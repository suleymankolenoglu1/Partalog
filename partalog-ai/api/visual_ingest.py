import os
import json
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# --- Router Değişikliği ---
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# --- API KEY İÇİN ---
from dotenv import load_dotenv

# --- YENİ GOOGLE SDK (v1.0+) ---
from google import genai
from google.genai import types

# .env dosyasını yükle
load_dotenv()

# ============================================
# LOGGING & CONFIG
# ============================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("PartalogAI")

DEBUG_DIR = "debug_dumps"
os.makedirs(DEBUG_DIR, exist_ok=True)

# MODEL AYARLARI (Şubat 2026 - En Güçlü Modeller)
GEMINI_MODEL_GLOBAL = "gemini-2.0-pro-exp-02-05" # Ana Beyin
GEMINI_MODEL_LOCAL = "gemini-2.0-flash"          # Hız Canavarı

HIGH_RES_TARGET = 3072 
RED = (255, 0, 0)
CIRCLE_RADIUS = 25
CIRCLE_THICKNESS = 6
FONT_SIZE = 40

# AYNI ANDA KAÇ PARÇA İŞLENSİN? (Rate Limit Koruması)
MAX_CONCURRENT_REQUESTS = 15 

# ============================================
# IMPORT REAL INFRA (MOCK - Senin dosyaların yoksa çalışsın diye)
# ============================================
try:
    from services.table_data import get_table_data
    from services.yolo_hotspots import get_yolo_hotspots
except ImportError:
    logger.warning("⚠️ Gerçek servisler bulunamadı, MOCK modunda çalışıyor.")
    async def get_table_data(img): return ['1', '2', '45', '12']
    async def get_yolo_hotspots(img): return [
        {'label':'1', 'bbox':[0.1, 0.1, 0.05, 0.05]},
        {'label':'45', 'bbox':[0.5, 0.5, 0.08, 0.08]}
    ]

# ============================================
# GOOGLE CLIENT SETUP (YENİ)
# ============================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    logger.error("🚨 GOOGLE_API_KEY bulunamadı! .env dosyasını kontrol et.")
    client = None
else:
    # Yeni Client Başlatma
    client = genai.Client(api_key=GOOGLE_API_KEY)

# ============================================
# UTILS
# ============================================
def resize_longest_side(image: Image.Image, target: int) -> Image.Image:
    w, h = image.size
    scale = target / max(w, h)
    if scale >= 1: return image
    return image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

def clamp01(v: float) -> float: return max(0.0, min(1.0, float(v)))

def pad_bbox(x1, y1, x2, y2, pad_ratio=0.2):
    w, h = x2 - x1, y2 - y1
    px, py = w * pad_ratio, h * pad_ratio
    return x1 - px, y1 - py, x2 + px, y2 + py

def crop_with_bbox(image: Image.Image, x1, y1, x2, y2) -> Image.Image:
    w, h = image.size
    px1, py1 = int(clamp01(x1)*w), int(clamp01(y1)*h)
    px2, py2 = int(clamp01(x2)*w), int(clamp01(y2)*h)
    return image.crop((max(0, px1), max(0, py1), min(w, px2), min(h, py2)))

def local_to_global(local_bbox, global_crop):
    lx1, ly1, lx2, ly2 = local_bbox
    gx1, gy1, gx2, gy2 = global_crop
    gw, gh = gx2 - gx1, gy2 - gy1
    return [
        clamp01(gx1 + lx1 * gw), clamp01(gy1 + ly1 * gh),
        clamp01(gx1 + lx2 * gw), clamp01(gy1 + ly2 * gh)
    ]

def draw_red_targets(image: Image.Image, hotspots: List[Dict]) -> Image.Image:
    img = image.copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    try: font = ImageFont.truetype("arial.ttf", FONT_SIZE)
    except: font = ImageFont.load_default()

    for hsp in hotspots:
        bx, by, bw, bh = hsp["bbox"]
        cx, cy = (bx + bw/2) * w, (by + bh/2) * h
        r = max(bw*w, bh*h) // 2 + 15
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=RED, width=CIRCLE_THICKNESS)
        draw.text((cx+r, cy-r), hsp["label"], fill=RED, font=font)
    return img

def dump_json(name: str, data: Any):
    try:
        path = os.path.join(DEBUG_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Dump error: {e}")

def robust_json_extract(text: str) -> Any:
    try:
        text = text.strip()
        match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
        if match: text = match.group(1)
        elif "```" in text: text = text.split("```")[1]
        return json.loads(text)
    except Exception as e:
        logger.error(f"JSON Parse Failed. Raw text sample: {text[:50]}...")
        return None

# ============================================
# GEMINI ENGINE (YENİ SDK - google.genai)
# ============================================

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), retry=retry_if_exception_type(Exception))
async def gemini_global_trace(image: Image.Image, labels: List[str]) -> List[Dict]:
    """AŞAMA 1: Global Tarama"""
    if not client: raise ValueError("API Key Missing")

    prompt = f"""
    ROLE: Senior Mechanical Engineer.
    TASK: Look at the RED CIRCLES marked on this technical drawing.
    TARGETS: {json.dumps(labels)}

    INSTRUCTIONS:
    1. Locate each RED CIRCLE matching the target labels.
    2. Follow the leader line from the circle to the part.
    3. Identify the ROUGH BOUNDING BOX containing the FULL part geometry (Head+Body).
    
    RETURN JSON:
    {{ "parts": [ {{ "label": "string", "rough_bbox": [ymin, xmin, ymax, xmax] }} ] }}
    * Coordinates must be 0-1 normalized.
    """
    
    # Yeni SDK Çağrısı
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL_GLOBAL,
        contents=[prompt, image],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    
    data = robust_json_extract(response.text)
    parts = data.get("parts", []) if data else []
    
    corrected = []
    for p in parts:
        if 'rough_bbox' in p and len(p['rough_bbox']) == 4:
            y1, x1, y2, x2 = p['rough_bbox']
            corrected.append({"label": p['label'], "rough_bbox": [x1, y1, x2, y2]})
    
    return corrected

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=5), retry=retry_if_exception_type(Exception))
async def gemini_local_refine(crop_img: Image.Image, label: str) -> Dict:
    """AŞAMA 2: Lokal İyileştirme"""
    if not client: raise ValueError("API Key Missing")

    prompt = f"""
    Ref: {label}
    Zoomed-in crop. Find PRECISE part boundaries. Ignore background noise.
    RETURN JSON: {{ "bbox": [ymin, xmin, ymax, xmax] }}
    """
    
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL_LOCAL,
        contents=[prompt, crop_img],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2
        )
    )
    
    data = robust_json_extract(response.text)
    if data and 'bbox' in data:
        y1, x1, y2, x2 = data['bbox']
        return {"label": label, "bbox": [x1, y1, x2, y2]}
    return None

# ============================================
# PIPELINE
# ============================================

async def hybrid_pipeline(page_image: Image.Image) -> List[Dict]:
    logger.info("🚀 Pipeline Başlatılıyor...")
    
    # 1. VERİ TOPLA
    table_data, yolo_hotspots = await asyncio.gather(
        get_table_data(page_image),
        get_yolo_hotspots(page_image)
    )

    # 2. FİLTRELE
    allowed = set(table_data)
    valid_hotspots = [h for h in yolo_hotspots if h["label"] in allowed]
    
    if not valid_hotspots:
        logger.warning("❌ Tablo ile eşleşen parça bulunamadı.")
        return []
    
    logger.info(f"✅ {len(valid_hotspots)} adet hedef parça işlenecek.")

    # 3. GÖRSEL İŞARETLEME
    high_res = resize_longest_side(page_image, HIGH_RES_TARGET)
    marked_img = draw_red_targets(high_res, valid_hotspots)
    marked_img.save(os.path.join(DEBUG_DIR, "debug_marked.jpg"))

    # 4. AŞAMA 1: GLOBAL TARAMA
    rough_results = await gemini_global_trace(marked_img, [h["label"] for h in valid_hotspots])
    dump_json("rough_results.json", rough_results)
    
    if not rough_results:
        logger.warning("⚠️ Stage 1 parça bulamadı.")
        return []

    # 5. AŞAMA 2: LOKAL İYİLEŞTİRME
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    async def refine_safe(item):
        async with semaphore: 
            try:
                label = item["label"]
                rx1, ry1, rx2, ry2 = item['rough_bbox']
                
                px1, py1, px2, py2 = pad_bbox(rx1, ry1, rx2, ry2, 0.2)
                px1, py1, px2, py2 = clamp01(px1), clamp01(py1), clamp01(px2), clamp01(py2)

                crop_img = crop_with_bbox(high_res, px1, py1, px2, py2)
                
                local_res = await gemini_local_refine(crop_img, label)
                
                if local_res:
                    global_bbox = local_to_global(local_res['bbox'], [px1, py1, px2, py2])
                    
                    w, h = high_res.size
                    gpx = [int(global_bbox[0]*w), int(global_bbox[1]*h), int(global_bbox[2]*w), int(global_bbox[3]*h)]
                    final_crop = high_res.crop((gpx[0], gpx[1], gpx[2], gpx[3]))
                    final_crop.save(os.path.join(DEBUG_DIR, f"final_{label}.jpg"))
                    
                    return {"label": label, "bbox": global_bbox}
            except Exception as e:
                logger.error(f"Refine Error ({item.get('label')}): {e}")
            return None

    tasks = [refine_safe(item) for item in rough_results]
    results = await asyncio.gather(*tasks)
    
    final_parts = [r for r in results if r is not None]
    dump_json("final_results.json", final_parts)
    
    logger.info(f"🏁 İşlem Tamamlandı. {len(final_parts)} parça başarıyla kesildi.")
    return final_parts

# ============================================
# API (ROUTER OLARAK DEĞİŞTİ)
# ============================================
router = APIRouter() # ✅ ARTIK ROUTER!

class IngestResult(BaseModel):
    parts: List[Dict]

@router.post("/visual-ingest", response_model=IngestResult)
async def visual_ingest(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        npimg = np.frombuffer(contents, np.uint8)
        cv_img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
        
        if cv_img is None: return IngestResult(parts=[])
        
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
        
        results = await hybrid_pipeline(pil_img)
        return IngestResult(parts=results)
    except Exception as e:
        logger.error(f"Critical Error: {e}")
        return IngestResult(parts=[])