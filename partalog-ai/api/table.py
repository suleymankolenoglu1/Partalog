"""
Table API - Gemini 2.0 Flash (Industrial Turkish Translation Mode 🇹🇷)
Görevi: Resmi okur, markayı bulur.
ÖZELLİK: Kaynak dil ne olursa olsun (Çince, Japonca, İngilizce) veriyi SANAYİ TÜRKÇESİNE çevirir.
"""

import aiohttp
import base64
import json
import io
import asyncio
import fitz  # ✅ PDF render
from PIL import Image
from fastapi import APIRouter, UploadFile, File, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from loguru import logger
import time
from config import settings

router = APIRouter()

# ✅ MODEL: gemini-2.0-flash (Hız ve Maliyet Dostu)
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"

# --- Modeller ---
class ProductResult(BaseModel):
    ref_number: str = Field(default="0")
    part_code: str
    part_name: str = Field(default="PARÇA")
    description: str = Field(default="")
    quantity: int = Field(default=1)
    dimensions: Optional[str] = None

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
    machine_brand: Optional[str] = None
    machine_group: str = "General"
    catalog_title: str

# --- Endpoints ---

@router.post("/extract-metadata", response_model=MetadataResponse)
async def extract_metadata(file: UploadFile = File(...)):
    logger.info("🔍 [METADATA] Kapak analizi (Zeka Modu) isteği geldi...")
    try:
        content = await file.read()
        image = Image.open(io.BytesIO(content)).convert("RGB")
        image.thumbnail((1024, 1024))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=90)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

        prompt = """
        You are an expert industrial sewing machine technician.
        Analyze this catalog cover image.
        
        TASK:
        1. Identify BRAND (JUKI, PEGASUS, YAMATO, TYPICAL, BROTHER, SIRUBA, JACK etc.)
        2. Identify MODEL (e.g. MF-7900, GK335)
        3. Identify MACHINE GROUP (Lockstitch, Overlock, Coverstitch, Chainstitch, Bartack, Buttonhole, General)

        Return JSON:
        { "machine_model": "...", "machine_brand": "...", "machine_group": "...", "catalog_title": "..." }
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}]}],
            "generationConfig": {"response_mime_type": "application/json", "temperature": 0.3}
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

                        machine_group = data.get("machine_group") or "General"

                        return MetadataResponse(
                            machine_model=data.get("machine_model", "Unknown"),
                            machine_brand=data.get("machine_brand"),
                            machine_group=machine_group,
                            catalog_title=data.get("catalog_title", "Unknown Catalog")
                        )

        return MetadataResponse(machine_model="Unknown", catalog_title="Error")
    except Exception as e:
        logger.error(f"Metadata Error: {e}")
        return MetadataResponse(machine_model="Error", catalog_title="Error")


@router.post("/extract", response_model=TableExtractionResponse)
async def extract_table(
    file: UploadFile = File(...),
    page_number: int = Query(default=1)
):
    start_time = time.time()
    logger.info(f"📄 [GEMINI] Tablo Okunuyor ve Türkçeye Çevriliyor: Sayfa {page_number}")
    
    try:
        content = await file.read()
        image = None

        # ✅ PDF mi?
        if content[:4] == b"%PDF":
            doc = fitz.open(stream=content, filetype="pdf")
            if page_number < 1 or page_number > doc.page_count:
                logger.error("❌ Sayfa numarası geçersiz")
                return _empty_response("Geçersiz sayfa")

            page = doc.load_page(page_number - 1)
            pix = page.get_pixmap(dpi=200)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        else:
            # ✅ Görsel (jpg/png) ise direkt aç
            image = Image.open(io.BytesIO(content)).convert("RGB")

        image.thumbnail((1500, 1500))
        buffered = io.BytesIO()
        image.save(buffered, format="JPEG", quality=95)
        base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

    except Exception as e:
        logger.error(f"❌ Resim hatası: {e}")
        return _empty_response()

    prompt_text = """
    You are Sewing Machine expert,Analyze this Sewing Machine Parts Catalog page. Extract the table into JSON.

    ROLE: You are an expert Turkish Industrial Sewing Machine Technician (40 years experience).

    🚨 CRITICAL TRANSLATION RULES (STRICT INDUSTRIAL JARGON):
    1. **TARGET LANGUAGE:** TURKISH (Sanayi Dili).
    2. **NO LITERAL TRANSLATION:** Never use Google Translate style. Use the terms used in a real workshop (Atölye).
       - ❌ WRONG: "Besleme Köpeği" (Feed Dog) -> ✅ RIGHT: "DİŞLİ"
       - ❌ WRONG: "Boğaz Plakası" (Throat Plate) -> ✅ RIGHT: "PLAKA" or "AYNA"
       - ❌ WRONG: "Hareketli Bıçak" (Movable Knife) -> ✅ RIGHT: "HAREKETLİ" (Bıçak zaten anlaşılırsa) or "HAREKETLİ BIÇAK"

    3. **UNIVERSAL INPUT:** If text is Chinese, Japanese, or English: Translate to TURKISH JARGON.
       - If text is already Turkish: Keep it uppercase.

    4. **NEVER RETURN UNKNOWN:** part_name MUST always be filled.
       - If the text is unclear, still infer the most likely Turkish workshop term.
       - Do NOT output "BİLİNMEYEN PARÇA", "UNKNOWN", or empty.

    5. **JARGON MAPPING (MEMORIZE THIS):**
       - "Feed Dog" / "送料牙" -> "DİŞLİ"
       - "Looper" / "弯针" -> "LÜPER"
       - "Needle Clamp" -> "İĞNE BAĞI"
       - "Presser Foot" / "压脚" -> "AYAK"
       - "Thread Take-up" -> "HOROZ"
       - "Tension Assembly" -> "TANSİYON"
       - "Bobbin Case" -> "MEKİK"
       - "Hook" -> "ÇAĞANOZ"
       - "Screw" -> "VİDA"
       - "Nut" -> "SOMUN"
       - "Washer" -> "PUL"
       - "Crank Shaft" -> "KRANK"

    OUTPUT RULES:
    1. **FORMAT:** JSON List only.
    2. **FIELDS:**
       - "ref_no": Reference number.
       - "part_code": Exact part code (Remove spaces, fix OCR errors).
       - "part_name": **THE TRANSLATED TURKISH NAME** (Uppercase).
       - "dimensions": Extract measurements (M4x10, 3/16, 5mm) to this field.
       - "qty": Quantity.

    RETURN JSON LIST ONLY. NO MARKDOWN.
    """

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt_text},
                {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
            ]
        }],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.1}
    }

    products = []
    
    async with aiohttp.ClientSession() as session:
        for attempt in range(3):
            try:
                async with session.post(GEMINI_API_URL, json=payload) as response:
                    if response.status == 200:
                        res = await response.json()
                        if not res.get("candidates"): break
                        
                        txt = res["candidates"][0]["content"]["parts"][0]["text"]
                        clean_txt = txt.replace("```json", "").replace("```", "").strip()
                        if clean_txt.endswith(",]"): clean_txt = clean_txt[:-2] + "]"
                        
                        try:
                            raw_data = json.loads(clean_txt)
                            for item in raw_data:
                                p_code = str(item.get("part_code") or "0").strip()
                                if len(p_code) < 3: continue 

                                dims = str(item.get("dimensions") or "").strip()
                                if dims.lower() in ["null", "none"]: dims = None

                                raw_name = str(item.get("part_name") or "").strip()
                                if not raw_name:
                                    raw_name = p_code

                                products.append(ProductResult(
                                    ref_number=str(item.get("ref_no") or "0"),
                                    part_code=p_code,
                                    part_name=raw_name.upper(),
                                    description=str(item.get("remarks") or "").strip(),
                                    quantity=1,
                                    dimensions=dims
                                ))
                            logger.success(f"✅ [GEMINI] {len(products)} parça TÜRKÇELEŞTİRİLDİ (Sayfa {page_number})")
                            break
                        except:
                            continue
                    else:
                        await asyncio.sleep(1)
            except Exception:
                await asyncio.sleep(1)

    return TableExtractionResponse(
        success=True,
        message=f"Gemini {len(products)} parçayı Türkçeye çevirip buldu.",
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