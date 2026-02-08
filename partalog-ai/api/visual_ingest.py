import io
import json
import base64
import fitz  # PyMuPDF
import aiohttp
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form
from pydantic import BaseModel, Field
from PIL import Image
from loguru import logger

from config import settings
from services.embedding import get_text_embedding
from services.vector_db import get_db_connection

router = APIRouter()

# ✅ Gemini Flash
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"

class VisualIngestResponse(BaseModel):
    total_pages: int
    total_parts_detected: int
    total_parts_updated: int
    skipped_no_match: int

def render_page_to_image(doc: fitz.Document, page_index: int) -> Image.Image:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=150)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

async def detect_parts_with_gemini(image: Image.Image) -> List[dict]:
    # image → base64
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=90)
    base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

    prompt = """
    You are a technical drawing analyzer for industrial spare parts catalogs.

    TASK:
    - Detect each individual part in the drawing.
    - For each part, return:
      1) label (the Ref number near the part if present)
      2) bbox (normalized 0-1 coordinates: x1,y1,x2,y2)
      3) ocr_text (technical text near the part if any)
      4) shape_tags (short tags like: "flange", "6-hole", "round", "plate")

    OUTPUT JSON FORMAT:
    {
      "parts": [
        {
          "label": "12",
          "bbox": { "x1": 0.12, "y1": 0.08, "x2": 0.32, "y2": 0.28 },
          "ocr_text": "M10x50",
          "shape_tags": ["flange", "6-hole", "round"]
        }
      ]
    }
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

    async with aiohttp.ClientSession() as session:
        async with session.post(GEMINI_API_URL, json=payload) as response:
            if response.status != 200:
                logger.error(f"Gemini error: {await response.text()}")
                return []
            data = await response.json()
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
            clean = raw.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
            return parsed.get("parts", [])

def crop_with_bbox(image: Image.Image, bbox: dict) -> Image.Image:
    w, h = image.size
    x1 = max(0, int(bbox["x1"] * w))
    y1 = max(0, int(bbox["y1"] * h))
    x2 = min(w, int(bbox["x2"] * w))
    y2 = min(h, int(bbox["y2"] * h))
    return image.crop((x1, y1, x2, y2))

@router.post("/visual-ingest", response_model=VisualIngestResponse)
async def visual_ingest(
    catalog_id: str = Form(...),
    file: UploadFile = File(...),
    page_start: int = Form(1),
    page_end: int = Form(0)
):
    """
    PDF -> teknik resimden parça yakalar, CatalogItems'e visual alanları yazar.
    """
    contents = await file.read()
    doc = fitz.open(stream=contents, filetype="pdf")
    total_pages = doc.page_count

    if page_end <= 0 or page_end > total_pages:
        page_end = total_pages

    total_parts_detected = 0
    total_parts_updated = 0
    skipped_no_match = 0

    conn = await get_db_connection()
    if not conn:
        raise RuntimeError("DB connection failed")

    try:
        for i in range(page_start - 1, page_end):
            page_number = i + 1
            image = render_page_to_image(doc, i)
            parts = await detect_parts_with_gemini(image)
            total_parts_detected += len(parts)

            for part in parts:
                label = (part.get("label") or "").strip()
                if not label:
                    skipped_no_match += 1
                    continue

                bbox = part.get("bbox") or {}
                ocr_text = (part.get("ocr_text") or "").strip()
                shape_tags = part.get("shape_tags") or []

                # Crop -> embedding (şimdilik text tabanlı)
                crop_image = crop_with_bbox(image, bbox)
                embedding_input = f"label:{label} ocr:{ocr_text} tags:{', '.join(shape_tags)}"
                visual_embedding = get_text_embedding(embedding_input)

                if not visual_embedding:
                    skipped_no_match += 1
                    continue

                # CatalogItems üzerinde güncelle
                update_sql = """
                    UPDATE "CatalogItems"
                    SET
                        "VisualEmbedding" = $1,
                        "VisualBbox" = $2,
                        "VisualShapeTags" = $3,
                        "VisualOcrText" = $4,
                        "VisualPageNumber" = $5,
                        "UpdatedDate" = NOW()
                    WHERE
                        "CatalogId" = $6
                        AND "PageNumber" = $7
                        AND "RefNumber" = $8
                    RETURNING "Id";
                """

                updated_id = await conn.fetchval(
                    update_sql,
                    str(visual_embedding),
                    json.dumps(bbox),
                    json.dumps(shape_tags),
                    ocr_text,
                    page_number,
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
            skipped_no_match=skipped_no_match
        )
    finally:
        await conn.close()