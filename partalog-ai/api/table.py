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
    ref_number: str = Field(default="0")
    part_code: str
    part_name: str = Field(default="Unknown Part") # Varsayılan değer eklendi
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

# 2. Metadata Modeli (Kapak Analizi İçin)
class MetadataResponse(BaseModel):
    machine_model: str
    catalog_title: str

# --- Endpoints ---

# A. KAPAK ANALİZİ
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


# B. TABLO AYIKLAMA (GÜNCELLENDİ - V3: TAM KORUMALI)
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
        image.thumbnail((1500, 1500)) # Okunabilirliği artırmak için çözünürlük artırıldı
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
    except Exception as e:
        logger.error(f"❌ Resim hatası: {e}")
        return _empty_response()

    # 2. PROMPT (GÜÇLENDİRİLDİ)
    prompt_text = """
    Analyze this Sewing Machine Parts Catalog page. Extract the table into JSON.

    CRITICAL RULES:
    1. **FIND THE PART NAME:** The Part Name is MANDATORY. It is usually to the right of the Part Code.
    2. **DO NOT LEAVE NAME EMPTY:** If you see text like "SCREW" or "NUT", that is the Name, NOT Remarks.
    3. **REMARKS vs NAME:** - "SCREW 1/8-44 L=6" -> Name: "SCREW", Remarks: "1/8-44 L=6"
       - If you are unsure, put EVERYTHING in "part_name". Better a long name than an empty one.
    4. **ACCURACY:** Part codes must be character-perfect (e.g. 133-50301).
    5. **NO TRANSLATION:** Keep text exactly as in the image (English).

    RETURN JSON FORMAT:
    [
      {
        "ref_no": "1", 
        "part_code": "13350301", 
        "part_name": "NEEDLE HEAD", 
        "remarks": "",
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

    # 3. İstek At (Retry Mekanizması)
    max_retries = 3       
    base_delay = 2       
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
                        try:
                            # Bazen JSON'un sonu bozuk gelebilir, onu düzeltiyoruz
                            if clean_txt.endswith(",]"): clean_txt = clean_txt[:-2] + "]"
                            raw_data = json.loads(clean_txt)
                        except:
                            # Çok bozuksa bir daha dene
                            continue
                            
                        logger.info(f"✅ Gemini {len(raw_data)} satır veri buldu (Sayfa {page_number})")
                        break
                    
                    elif response.status in [429, 503]:
                        wait_time = (base_delay * (1.5 ** attempt))
                        logger.warning(f"⏳ Kota Doldu. {wait_time:.1f}sn bekleniyor...")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"❌ API Hatası: {response.status}")
                        break
            except Exception as e:
                logger.error(f"❌ Bağlantı Hatası: {e}")
                await asyncio.sleep(1)
                continue

    if len(raw_data) > 300: # Index sayfası koruması
        return _empty_response(f"Index sayfası ({len(raw_data)} satır).")

    products = []
    for item in raw_data:
        try:
            # Code Cleaning
            p_code = str(item.get("part_code") or item.get("Part Number") or item.get("code") or "").strip()
            if len(p_code) < 2: continue # Çok kısa kodları atla

            # Ref No Cleaning
            ref_raw = str(item.get("ref_no") or item.get("ref") or "0")
            
            # 🔥 SİGORTA MEKANİZMASI (SMART FALLBACK) 🔥
            p_name = str(item.get("part_name") or item.get("description") or "").strip()
            p_desc = str(item.get("remarks") or item.get("gauge") or "").strip()

            # Senaryo 1: İsim BOŞ ama Açıklama DOLU ise -> Açıklamayı isim yap
            if not p_name and p_desc:
                p_name = p_desc
                # p_desc = "" # Açıklamayı silmiyoruz, kalsın

            # Senaryo 2: İsim HALA BOŞ ise -> "Unknown Part" yap
            if not p_name:
                p_name = "Unknown Part"

            # Qty Cleaning
            qty_raw = str(item.get("qty") or "1")
            qty_clean = ''.join(filter(str.isdigit, qty_raw))
            qty_val = int(qty_clean) if qty_clean else 1

            products.append(ProductResult(
                ref_number=ref_raw, 
                part_code=p_code,
                part_name=p_name,
                description=p_desc, 
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