import aiohttp
import base64
import json
import io
import asyncio
from PIL import Image
from fastapi import APIRouter, UploadFile, File
from loguru import logger
from config import settings

router = APIRouter()

# 🚀 HIZ AYARI: Aynı anda 10 sayfaya kadar işlem yapabilir
CONCURRENCY_LIMIT = asyncio.Semaphore(10)

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite-preview-02-05:generateContent?key={settings.GEMINI_API_KEY}"

@router.post("/analyze-page-title")
async def analyze_page_title(file: UploadFile = File(...)):
    async with CONCURRENCY_LIMIT:
        # Tier 1 olduğumuz için beklemeye gerek yok, akışkan olsun
        await asyncio.sleep(0.1) 

        try:
            image_bytes = await file.read()
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            
            # Görüntü kalitesini optimize et (Tablo okuma doğruluğu için önemli)
            image.thumbnail((1024, 1024)) 
            buffered = io.BytesIO()
            image.save(buffered, format="JPEG", quality=90) 
            base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

            # 🧠 HASSAS TERAZİ PROMPT: Resim ve Tabloyu Keskin Ayırır
            prompt_text = """
You are a strict classifier for spare parts catalogs. Analyze this page image.
Return ONLY raw JSON.

LANGUAGE RULE:
- Translate the "title" and "part_name" into TURKISH. 
- Example: "CYLINDER HEAD COMPONENTS" -> "SİLİNDİR KAPAĞI BİLEŞENLERİ"
- Example: "SCREW" -> "VİDA", "GASKET" -> "CONTA".

CLASSIFICATION RULES (PRECISION MODE):

1. CHECK FOR "TECHNICAL DRAWING" (Exploded View):
   - DOES IT HAVE A DIAGRAM? If the page contains a technical illustration, schema, or exploded view of parts (lines pointing to numbers), it is a DRAWING.
   - DOMINANCE RULE: Even if there is a small list/legend in the corner, if the MAIN feature is a diagram, set "is_technical_drawing": true.
   - ACTION: Return "parts": []. 

2. CHECK FOR "PARTS LIST" (Table):
   - IS IT A GRID? If the page is primarily a structured table with rows and columns (Ref No, Part No, Description), it is a PARTS LIST.
   - ACTION: Set "is_parts_list": true.
   - EXTRACT DATA: Extract ALL rows from the table. 
   - TRANSLATE: Ensure "part_name" is in Turkish.

3. "title": Extract and TRANSLATE the main assembly header to TURKISH.

JSON OUTPUT FORMAT:
{
  "is_technical_drawing": boolean,
  "is_parts_list": boolean,
  "title": "TURKISH_TRANSLATED_STRING",
  "parts": [
    { "ref_number": 1, "part_code": "ABC-123", "part_name": "TURKISH_NAME", "quantity": 1 }
  ]
}
"""

            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt_text},
                        {"inline_data": {"mime_type": "image/jpeg", "data": base64_image}}
                    ]
                }],
                "generationConfig": { "response_mime_type": "application/json" }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(GEMINI_API_URL, json=payload) as response:
                    if response.status == 200:
                        result_json = await response.json()
                        raw_text = result_json["candidates"][0]["content"]["parts"][0]["text"]
                        clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                        return json.loads(clean_text)
                    
                    # API hatası durumunda boş dön
                    logger.error(f"AI API Hatası: {response.status}")
                    return {"is_technical_drawing": False, "is_parts_list": False, "title": None, "parts": []}

        except Exception as e:
            logger.error(f"Sistem Hatası: {e}")
            return {"is_technical_drawing": False, "is_parts_list": False, "title": None, "parts": []}