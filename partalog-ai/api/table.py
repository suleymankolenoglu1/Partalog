"""
Table API - Gemini 2.0 Flash (Pure Reader Mode)
Görevi: Resmi okuyup veriyi C#'a teslim etmek. Veritabanına YAZMAZ.
"""

import aiohttp
import base64
import json
import io
import asyncio
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Query
from pydantic import BaseModel, Field
from typing import List
from loguru import logger
import time
from config import settings

router = APIRouter()

# ✅ MODEL: gemini-2.0-flash-lite
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"

# --- Modeller (C# Tarafıyla Uyumlu) ---

class ProductResult(BaseModel):
    ref_number: str = Field(default="0")
    part_code: str
    part_name: str = Field(default="Unknown Part")
    description: str = Field(default="")
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

class MetadataResponse(BaseModel):
    machine_model: str
    catalog_title: str

# --- Endpoints ---

# A. KAPAK ANALİZİ (C# Kullanıyor)
@router.post("/extract-metadata", response_model=MetadataResponse)
async def extract_metadata(file: UploadFile = File(...)):
    """
    Sadece 1. sayfayı (Kapağı) okur ve Makine Modelini bulur.
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
                    candidates = res.get("candidates", [])
                    if candidates:
                        txt = candidates[0]["content"]["parts"][0]["text"]
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


# B. TABLO AYIKLAMA (Veritabanı kodu yok, saf okuyucu)
@router.post("/extract", response_model=TableExtractionResponse)
async def extract_table(
    file: UploadFile = File(...),
    page_number: int = Query(default=1)
):
    start_time = time.time()
    logger.info(f"📄 [GEMINI] Tablo Okunuyor: Sayfa {page_number}")
    
    # 1. Dosya İşleme
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        image.thumbnail((1500, 1500))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"❌ Resim hatası: {e}")
        return _empty_response()

    # 2. PROMPT
    prompt_text = """
    Analyze this Sewing Machine Parts Catalog page. Extract the table into JSON.

    CRITICAL RULES:
    1. **FIND THE PART NAME:** The Part Name is MANDATORY.
    2. **REMARKS vs NAME:** If you are unsure, put EVERYTHING in "part_name".
    3. **ACCURACY:** Part codes must be character-perfect.
    4. **NO TRANSLATION:** Keep text exactly as in the image (English).

    RETURN JSON FORMAT:
    [
      {"ref_no": "1", "part_code": "13350301", "part_name": "NEEDLE HEAD", "remarks": "", "qty": "1"}
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

    # 3. İstek At (Retry Mekanizması)
    max_retries = 3
    base_delay = 2
    products = []

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
                        if clean_txt.endswith(",]"): clean_txt = clean_txt[:-2] + "]"
                        
                        try:
                            raw_data = json.loads(clean_txt)
                            
                            # JSON Dönüşümü
                            for item in raw_data:
                                p_code = str(item.get("part_code") or item.get("Part Number") or item.get("code") or "").strip()
                                if len(p_code) < 2: continue

                                products.append(ProductResult(
                                    ref_number=str(item.get("ref_no") or item.get("ref") or "0"),
                                    part_code=p_code,
                                    part_name=str(item.get("part_name") or item.get("description") or "Unknown Part").strip(),
                                    description=str(item.get("remarks") or item.get("gauge") or "").strip(),
                                    quantity=1
                                ))
                            logger.success(f"✅ [GEMINI] {len(products)} parça bulundu (Sayfa {page_number})")
                            break # Başarılıysa döngüden çık
                        except:
                            continue # JSON bozuksa tekrar dene

                    elif response.status in [429, 503]:
                        await asyncio.sleep(base_delay * (1.5 ** attempt))
                        continue
                    else:
                        break
            except Exception as e:
                await asyncio.sleep(1)
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