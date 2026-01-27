"""
Table API - Gemini 2.0 Flash (Slow & Stable Mode)
"""

import aiohttp
import base64
import json
import io
import asyncio
import random
from PIL import Image
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from loguru import logger
import time
from config import settings

router = APIRouter()

# ✅ MODEL: gemini-2.0-flash (Senin hesabında bu var)
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-preview-02-05:generateContent?key={settings.GEMINI_API_KEY}"

# --- Schemas ---
class ProductResult(BaseModel):
    ref_number: int = Field(default=0)
    part_code: str
    part_name: str
    quantity: int = Field(default=1)

class TableResult(BaseModel):
    row_count: int
    products: List[ProductResult]

class TableExtractionResponse(BaseModel):
    success: bool
    message: str
    total_products: int
    tables: List[TableResult]

# --- Endpoint ---
@router.post("/extract", response_model=TableExtractionResponse)
async def extract_table(
    file: UploadFile = File(...),
    page_number: int = Query(default=1)
):
    start_time = time.time()
    logger.info(f"📄 Tablo Okuma Başladı: Sayfa {page_number}")
    
    # 1. Dosya İşleme
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        image.thumbnail((1024, 1024))
        
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=90)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"❌ Resim hatası: {e}")
        return _empty_response()

    # 2. PROMPT
    prompt_text = """
Extract the Spare Parts Table from this image.

RULES:
1. Look for a table structure.
2. Extract columns: Ref No, Part Code, Description, Qty.
3. LANGUAGE: Translate the "description" (part name) into TURKISH. 
   - Example: "Oil Filter" -> "Yağ Filtresi".
4. Return pure JSON array.

RETURN RAW JSON ARRAY:
[{"ref_no": "1", "part_code": "ABC", "description": "TÜRKÇE_AD", "qty": "1"}, ...]
"""

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
            ]
        }],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    # 3. İstek At (TURTLE MODE 🐢)
    # Gemini 2.0 Flash'ın kotası hassas olduğu için bekleme sürelerini artırdık.
    max_retries = 5       # Daha fazla deneme hakkı
    base_delay = 10       # Hata alınca minimum 10 saniye bekle
    raw_data = []

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.post(GEMINI_API_URL, json=payload) as response:
                    if response.status == 200:
                        res = await response.json()
                        if not res.get("candidates"): 
                            logger.warning(f"⚠️ Gemini boş cevap döndü (Sayfa {page_number})")
                            break
                        
                        txt = res["candidates"][0]["content"]["parts"][0]["text"]
                        clean_txt = txt.replace("```json", "").replace("```", "").strip()
                        raw_data = json.loads(clean_txt)
                        logger.info(f"✅ Gemini {len(raw_data)} satır veri buldu (Sayfa {page_number})")
                        break
                    
                    elif response.status in [429, 503]:
                        # Logaritmik Bekleme: 10sn -> 20sn -> 40sn -> 80sn
                        wait_time = (base_delay * (2 ** attempt)) + (random.randint(0, 1000) / 1000)
                        logger.warning(f"⏳ Kota Hatası ({response.status}). {wait_time:.1f}sn bekleniyor... (Deneme {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    else:
                        logger.error(f"❌ API Hatası: {response.status}")
                        break
            except Exception as e:
                logger.error(f"❌ Bağlantı Hatası: {e}")
                break

    # 4. Limit Kontrolü (Gevşetildi: 200)
    if len(raw_data) > 200:
        logger.warning(f"⚠️ ÇOK FAZLA VERİ ({len(raw_data)}). Index sanılıp siliniyor.")
        return _empty_response(f"Index sayfası ({len(raw_data)} satır).")

    products = []
    for item in raw_data:
        try:
            p_code = str(item.get("part_code") or item.get("Part Number") or "").strip()
            if len(p_code) < 2: continue

            ref_raw = str(item.get("ref_no") or item.get("ref") or "0")
            ref_clean = ''.join(filter(str.isdigit, ref_raw))
            ref_val = int(ref_clean) if ref_clean else 0
            
            # Ref No 0 olsa bile alıyoruz (bazı tablolarda RefNo olmayabilir)
            
            qty_raw = str(item.get("qty") or item.get("quantity") or "1")
            qty_clean = ''.join(filter(str.isdigit, qty_raw))
            qty_val = int(qty_clean) if qty_clean else 1

            products.append(ProductResult(
                ref_number=ref_val,
                part_code=p_code,
                part_name=str(item.get("description") or "").strip(),
                quantity=qty_val
            ))
        except:
            continue

    logger.info(f"📦 İşlenen Ürün Sayısı: {len(products)} (Sayfa {page_number})")

    return TableExtractionResponse(
        success=True,
        message=f"Gemini {len(products)} parça buldu.",
        total_products=len(products),
        tables=[TableResult(row_count=len(products), products=products)],
        page_number=page_number,
        processing_time_ms=0
    )

def _empty_response(msg="Boş"):
    return TableExtractionResponse(
        success=True, message=msg, total_products=0, 
        tables=[TableResult(row_count=0, products=[])], 
        page_number=0, processing_time_ms=0
    )