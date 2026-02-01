"""
Table API - Gemini 2.0 Flash (Library Builder Mode)
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

# ✅ MODEL: gemini-2.0-flash-lite
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"
# --- Schemas ---

# 1. Parça Sonuç Modeli (GÜNCELLENDİ)
class ProductResult(BaseModel):
    ref_number: str = Field(default="0") # String yaptık ("12-1" gibi ref no olabilir)
    part_code: str
    part_name: str
    description: str = Field(default="") # 🔥 YENİ: "FOR B48" gibi özellikler buraya
    quantity: int = Field(default=1)

class TableResult(BaseModel):
    row_count: int
    products: List[ProductResult]

class TableExtractionResponse(BaseModel):
    success: bool
    message: str
    total_products: int
    tables: List[TableResult]
    page_number: int = 0
    processing_time_ms: float = 0

# 2. Metadata Modeli (Kapak Analizi İçin)
class MetadataResponse(BaseModel):
    machine_model: str
    catalog_title: str

# --- Endpoints ---

# A. KAPAK ANALİZİ (YENİ ENDPOINT)
@router.post("/extract-metadata", response_model=MetadataResponse)
async def extract_metadata(file: UploadFile = File(...)):
    """
    Sadece 1. sayfayı (Kapağı) okur ve Makine Modelini bulur.
    Örn: "MF-7500-C11"
    """
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        image.thumbnail((1024, 1024))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=90)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

        prompt = """
        Analyze this catalog cover page image.
        Extract:
        1. The Main Machine Model Code (e.g., MF-7500, DDL-8700).
        2. The Catalog Title or List No (e.g., 1611-01).

        Return JSON:
        {"machine_model": "MF-7500-C11", "catalog_title": "PARTS LIST 1611-01"}
        """

        payload = {
            "contents": [{
                "parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}]
            }],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as response:
                if response.status == 200:
                    res = await response.json()
                    txt = res["candidates"][0]["content"]["parts"][0]["text"]
                    clean_txt = txt.replace("```json", "").replace("```", "").strip()
                    data = json.loads(clean_txt)
                    return MetadataResponse(
                        machine_model=data.get("machine_model", "Unknown"),
                        catalog_title=data.get("catalog_title", "Unknown Catalog")
                    )
        return MetadataResponse(machine_model="Unknown", catalog_title="Unknown")
    except Exception as e:
        logger.error(f"Metadata Error: {e}")
        return MetadataResponse(machine_model="Error", catalog_title="Error")


# B. TABLO AYIKLAMA (GÜNCELLENDİ)
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

    # 2. PROMPT (GÜNCELLENDİ: Nitelik Ayrıştırma)
    # Artık "Remarks" (Özellik) sütununu ayrı istiyoruz.
    prompt_text = """
    Extract the Spare Parts Table from this image into a clean JSON structure.

    STRICT RULES:
    1. **COLUMNS:** Identify Ref No, Part Code, Part Name, and Remarks (Gauge/Spec).
    2. **SPLIT NAMES:** If a line says "THROAT PLATE FOR B48", split it:
       - part_name: "THROAT PLATE"
       - remarks: "FOR B48"
    3. **NO TRANSLATION:** Keep English terms exactly as seen.
    4. **ACCURACY:** Part codes must be character-perfect.
    
    RETURN JSON FORMAT:
    [
      {
        "ref_no": "1", 
        "part_code": "13353909", 
        "part_name": "MAIN FEED DOG", 
        "remarks": "FOR B56",
        "qty": "1"
      }
    ]
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
    max_retries = 5       
    base_delay = 5       
    raw_data = []

    async with aiohttp.ClientSession() as session:
        for attempt in range(max_retries):
            try:
                async with session.post(GEMINI_API_URL, json=payload) as response:
                    if response.status == 200:
                        res = await response.json()
                        if not res.get("candidates"): 
                            break
                        
                        txt = res["candidates"][0]["content"]["parts"][0]["text"]
                        clean_txt = txt.replace("```json", "").replace("```", "").strip()
                        raw_data = json.loads(clean_txt)
                        logger.info(f"✅ Gemini {len(raw_data)} satır veri buldu (Sayfa {page_number})")
                        break
                    
                    elif response.status in [429, 503]:
                        wait_time = (base_delay * (1.5 ** attempt)) + (random.randint(0, 1000) / 1000)
                        logger.warning(f"⏳ Kota Doldu. {wait_time:.1f}sn bekleniyor...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ API Hatası: {response.status}")
                        break
            except Exception as e:
                logger.error(f"❌ Bağlantı Hatası: {e}")
                await asyncio.sleep(2)
                continue

    if len(raw_data) > 250:
        return _empty_response(f"Index sayfası ({len(raw_data)} satır).")

    products = []
    for item in raw_data:
        try:
            # Code Cleaning
            p_code = str(item.get("part_code") or item.get("Part Number") or item.get("code") or "").strip()
            if len(p_code) < 2: continue

            # Ref No Cleaning
            ref_raw = str(item.get("ref_no") or item.get("ref") or "0")
            
            # Name & Remarks Cleaning
            p_name = str(item.get("part_name") or item.get("description") or "").strip()
            p_desc = str(item.get("remarks") or item.get("gauge") or "").strip() # 🔥 Burası Yeni

            # Qty Cleaning
            qty_raw = str(item.get("qty") or "1")
            qty_clean = ''.join(filter(str.isdigit, qty_raw))
            qty_val = int(qty_clean) if qty_clean else 1

            products.append(ProductResult(
                ref_number=ref_raw, # String olarak saklıyoruz
                part_code=p_code,
                part_name=p_name,
                description=p_desc, # C# tarafındaki 'Description' alanına gidecek
                quantity=qty_val
            ))
        except:
            continue

    return TableExtractionResponse(
        success=True,
        message=f"Gemini {len(products)} parça buldu.",
        total_products=len(products),
        tables=[TableResult(row_count=len(products), products=products)],
        page_number=page_number,
        processing_time_ms=round((time.time() - start_time) * 1000, 2)
    )

def _empty_response(msg="Boş"):
    return TableExtractionResponse(
        success=True, message=msg, total_products=0, 
        tables=[TableResult(row_count=0, products=[])], 
        page_number=0, processing_time_ms=0
    )