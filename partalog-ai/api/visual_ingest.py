import base64
import io
import json
import uuid
import asyncio
from typing import List, Optional

import aiohttp
import fitz
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from loguru import logger
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel

from config import settings
from services.embedding import get_text_embedding
from services.storage.storage_factory import save_file
from services.vector_db import get_db_connection

router = APIRouter()

# ✅ Daha zeki model opsiyonu
GEMINI_VISUAL_MODEL = getattr(settings, "GEMINI_VISUAL_MODEL", "gemini-3-pro-preview")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_VISUAL_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
)

# 🔥 Görsel kalite ayarları
RENDER_DPI = 450
CROP_PADDING_RATIO = 0.04
CROP_MIN_SIZE = 300
SHARPEN_ENABLED = True

# ✅ Minimum bbox alanı (normalize)
MIN_BBOX_AREA = 0.0005  # örn: %0.05

# ✅ Çıktı formatı
OUTPUT_FORMAT = "PNG"
OUTPUT_EXTENSION = "png"

# ✅ YOLO tespit için bytes formatı
DETECT_FORMAT = "PNG"

# ✅ Gemini timeout
GEMINI_TIMEOUT_SECONDS = 30

class VisualIngestResponse(BaseModel):
    total_pages: int
    total_parts_detected: int
    total_parts_updated: int
    skipped_no_match: int
    skipped_non_technical: int

# ✅ Sayfa bazlı Gemini cache
_PAGE_CACHE = {}

def get_models():
    """Ana uygulamadan model referanslarını al."""
    from main import models
    return models

def render_page_to_image(doc: fitz.Document, page_index: int) -> Image.Image:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=RENDER_DPI, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def enhance_image(image: Image.Image) -> Image.Image:
    image = ImageOps.autocontrast(image, cutoff=1)
    if SHARPEN_ENABLED:
        image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=3))
    return image

def image_to_bytes(image: Image.Image, fmt: str = "PNG", quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    if fmt.upper() == "JPEG":
        image.save(buffer, format="JPEG", quality=quality, subsampling=0)
    else:
        image.save(buffer, format=fmt, optimize=True)
    return buffer.getvalue()

def normalize_ref(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip().upper().replace(" ", "")
    if cleaned.isdigit():
        cleaned = str(int(cleaned))
    return cleaned

def clamp_bbox(bbox: dict) -> dict:
    return {
        "x1": max(0.0, min(1.0, float(bbox.get("x1", 0)))),
        "y1": max(0.0, min(1.0, float(bbox.get("y1", 0)))),
        "x2": max(0.0, min(1.0, float(bbox.get("x2", 0)))),
        "y2": max(0.0, min(1.0, float(bbox.get("y2", 0)))),
    }

def is_valid_bbox(bbox: dict) -> bool:
    try:
        x1, y1, x2, y2 = bbox["x1"], bbox["y1"], bbox["x2"], bbox["y2"]
        return x2 > x1 and y2 > y1
    except Exception:
        return False

def bbox_area(bbox: dict) -> float:
    try:
        return max(0.0, (bbox["x2"] - bbox["x1"]) * (bbox["y2"] - bbox["y1"]))
    except Exception:
        return 0.0

def bbox_center(bbox: dict) -> Optional[tuple]:
    try:
        return ((bbox["x1"] + bbox["x2"]) / 2, (bbox["y1"] + bbox["y2"]) / 2)
    except Exception:
        return None

def crop_with_bbox(image: Image.Image, bbox: dict, padding_ratio: float = CROP_PADDING_RATIO) -> Image.Image:
    w, h = image.size
    x1 = max(0, int(bbox["x1"] * w))
    y1 = max(0, int(bbox["y1"] * h))
    x2 = min(w, int(bbox["x2"] * w))
    y2 = min(h, int(bbox["y2"] * h))

    pad_x = int((x2 - x1) * padding_ratio)
    pad_y = int((y2 - y1) * padding_ratio)

    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)

    crop = image.crop((x1, y1, x2, y2))

    if min(crop.size) < CROP_MIN_SIZE:
        scale = CROP_MIN_SIZE / min(crop.size)
        new_size = (int(crop.width * scale), int(crop.height * scale))
        crop = crop.resize(new_size, Image.LANCZOS)

    return crop

def detect_balloons_with_yolo(image: Image.Image):
    """YOLO ile balon tespiti + OCR label okuma (tek sayfa)."""
    models = get_models()
    detector = models.get("yolo")
    ocr = models.get("ocr")

    if detector is None:
        raise HTTPException(
            status_code=503,
            detail="YOLO modeli yüklenmemiş. models/best.pt dosyasını kontrol edin."
        )

    image_bytes = image_to_bytes(image, fmt=DETECT_FORMAT)
    detections, cv_image = detector.detect_from_bytes(image_bytes, settings.YOLO_CONFIDENCE)

    img_h, img_w = cv_image.shape[:2]
    balloons = []

    for det in detections:
        label = None

        if ocr is not None:
            try:
                padding = 6
                x1 = max(0, int(det.x1) - padding)
                y1 = max(0, int(det.y1) - padding)
                x2 = min(img_w, int(det.x2) + padding)
                y2 = min(img_h, int(det.y2) + padding)

                crop = cv_image[y1:y2, x1:x2].copy()
                if crop.size > 0:
                    label = ocr.read_number(crop)
            except Exception as e:
                logger.warning(f"OCR hatası: {e}")

        if not label:
            continue

        center_x = (det.x1 + det.x2) / 2
        center_y = (det.y1 + det.y2) / 2

        balloons.append({
            "label": str(label),
            "x": round(center_x / img_w, 6),
            "y": round(center_y / img_h, 6),
        })

    return balloons

def match_parts_to_balloons(parts: List[dict], balloons: List[dict]) -> List[dict]:
    if not parts or not balloons:
        return parts

    used = set()

    def nearest_balloon_index(cx, cy, candidates):
        best_idx = None
        best_dist = 1e9
        for idx in candidates:
            if idx in used:
                continue
            bx, by = balloons[idx]["x"], balloons[idx]["y"]
            dist = (bx - cx) ** 2 + (by - cy) ** 2
            if dist < best_dist:
                best_dist = dist
                best_idx = idx
        return best_idx

    for part in parts:
        bbox = part.get("bbox") or {}
        center = bbox_center(bbox)
        if not center:
            continue

        cx, cy = center
        label = (part.get("label") or "").strip()

        if label:
            candidates = [i for i, b in enumerate(balloons) if b.get("label") == label]
            if candidates:
                idx = nearest_balloon_index(cx, cy, candidates)
                if idx is not None:
                    used.add(idx)
                    continue

        idx = nearest_balloon_index(cx, cy, range(len(balloons)))
        if idx is not None:
            used.add(idx)
            part["label"] = balloons[idx]["label"]

    return parts

async def detect_parts_with_gemini_batch(image: Image.Image, balloons: List[dict], cache_key: str) -> List[dict]:
    if not balloons:
        return []

    if cache_key in _PAGE_CACHE:
        logger.info(f"🧠 Gemini cache hit: {cache_key}")
        return _PAGE_CACHE[cache_key]

    base64_image = base64.b64encode(image_to_bytes(image, fmt="JPEG", quality=90)).decode("utf-8")

    prompt = f"""
    You are a technical drawing analyzer.

    Given the full page image, you will receive a list of balloon points (normalized 0..1).
    For EACH balloon point, follow the arrow that originates from it and return a tight bounding box
    around the referenced part.

    IMPORTANT:
    - ALWAYS return the same "label" value given in Balloon points.

    Return ONLY JSON:
    {{
      "parts": [
        {{ "label": "12", "bbox": {{ "x1": 0.12, "y1": 0.08, "x2": 0.32, "y2": 0.28 }} }}
      ]
    }}

    Balloon points:
    {json.dumps(balloons, ensure_ascii=False)}
    """

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
            ]
        }],
        "generationConfig": { "response_mime_type": "application/json", "temperature": 0.2 }
    }

    last_error = None
    for attempt in range(2):
        try:
            timeout = aiohttp.ClientTimeout(total=GEMINI_TIMEOUT_SECONDS)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(GEMINI_API_URL, json=payload) as response:
                    if response.status != 200:
                        last_error = await response.text()
                        logger.warning(f"Gemini error (attempt {attempt+1}): {last_error}")
                    else:
                        data = await response.json()
                        raw = data["candidates"][0]["content"]["parts"][0]["text"]
                        clean = raw.replace("```json", "").replace("```", "").strip()
                        parsed = json.loads(clean)
                        _PAGE_CACHE[cache_key] = parsed.get("parts", [])
                        return _PAGE_CACHE[cache_key]
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Gemini exception (attempt {attempt+1}): {e}")

        await asyncio.sleep(0.5)

    logger.error(f"Gemini failed after retry: {last_error}")
    return []

@router.post("/visual-ingest", response_model=VisualIngestResponse)
async def visual_ingest(
    catalog_id: str = Form(...),
    file: UploadFile = File(...),
    page_start: int = Form(1),
    page_end: int = Form(0),
    technical_pages: str = Form("[]"),
    allowed_refs_map: str = Form("{}")
):
    contents = await file.read()
    doc = fitz.open(stream=contents, filetype="pdf")
    total_pages = doc.page_count

    if page_end <= 0 or page_end > total_pages:
        page_end = total_pages

    try:
        technical_pages_list = json.loads(technical_pages) or []
    except Exception:
        technical_pages_list = []

    try:
        allowed_refs_raw = json.loads(allowed_refs_map) or {}
    except Exception:
        allowed_refs_raw = {}

    allowed_refs_by_page = {}
    for page_key, refs in allowed_refs_raw.items():
        try:
            page_num = int(page_key)
        except (TypeError, ValueError):
            continue
        if not isinstance(refs, list):
            continue

        normalized_refs = {normalize_ref(r) for r in refs if normalize_ref(r)}
        allowed_refs_by_page[page_num] = normalized_refs

    total_parts_detected = 0
    total_parts_updated = 0
    skipped_no_match = 0
    skipped_non_technical = 0

    conn = await get_db_connection()
    if not conn:
        raise RuntimeError("DB connection failed")

    try:
        for i in range(page_start - 1, page_end):
            page_number = i + 1

            if technical_pages_list and page_number not in technical_pages_list:
                skipped_non_technical += 1
                continue

            image = render_page_to_image(doc, i)
            image = enhance_image(image)

            balloons = detect_balloons_with_yolo(image)
            if not balloons:
                logger.info(f"⚠️ Sayfa {page_number}: balon bulunamadı.")
                continue

            cache_key = f"{catalog_id}:{page_number}:{len(balloons)}"
            parts = await detect_parts_with_gemini_batch(image, balloons, cache_key)
            parts = match_parts_to_balloons(parts, balloons)

            filtered_parts = []
            for part in parts:
                bbox = part.get("bbox") or {}
                bbox = clamp_bbox(bbox)
                if not is_valid_bbox(bbox):
                    continue
                if bbox_area(bbox) < MIN_BBOX_AREA:
                    continue
                part["bbox"] = bbox
                filtered_parts.append(part)

            parts = filtered_parts
            logger.info(f"📌 Sayfa {page_number}: balon={len(balloons)} → bbox={len(parts)}")
            total_parts_detected += len(parts)

            allowed_refs = allowed_refs_by_page.get(page_number)

            for part in parts:
                label = (part.get("label") or "").strip()
                bbox = part.get("bbox") or {}

                if not label or not bbox:
                    skipped_no_match += 1
                    continue

                if allowed_refs is not None:
                    if normalize_ref(label) not in allowed_refs:
                        skipped_no_match += 1
                        continue

                crop_image = crop_with_bbox(image, bbox)
                embedding_input = f"label:{label} tags:gemini_bbox"
                visual_embedding = get_text_embedding(embedding_input)

                if not visual_embedding:
                    skipped_no_match += 1
                    continue

                buffered = io.BytesIO()
                crop_image.save(
                    buffered,
                    format=OUTPUT_FORMAT,
                    optimize=True
                )

                object_key = f"{catalog_id}/{page_number}/{label}-{uuid.uuid4().hex}.{OUTPUT_EXTENSION}"
                visual_image_url = save_file(buffered.getvalue(), object_key)

                update_sql = """
                    UPDATE "CatalogItems"
                    SET
                        "VisualEmbedding" = $1,
                        "VisualBbox" = $2,
                        "VisualShapeTags" = $3,
                        "VisualOcrText" = $4,
                        "VisualPageNumber" = $5,
                        "VisualImageUrl" = $6,
                        "UpdatedDate" = NOW()
                    WHERE
                        "CatalogId" = $7
                        AND "PageNumber" = $8
                        AND "RefNumber" = $9
                    RETURNING "Id";
                """

                updated_id = await conn.fetchval(
                    update_sql,
                    str(visual_embedding),
                    json.dumps(bbox),
                    json.dumps([]),
                    "",
                    page_number,
                    visual_image_url,
                    catalog_id,
                    str(page_number),
                    label
                )

                if updated_id:
                    total_parts_updated += 1
                else:
                    skipped_no_match += 1

        return VisualIngestResponse(
            total_pages=total_pages,
            total_parts_detected=total_parts_detected,
            total_parts_updated=total_parts_updated,
            skipped_no_match=skipped_no_match,
            skipped_non_technical=skipped_non_technical
        )
    finally:
        await conn.close()