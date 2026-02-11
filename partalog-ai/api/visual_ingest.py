import base64
import io
import json
import uuid
from typing import List

import aiohttp
import fitz
from fastapi import APIRouter, UploadFile, File, Form
from loguru import logger
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel

from config import settings
from services.embedding import get_text_embedding
from services.storage.storage_factory import save_file
from services.vector_db import get_db_connection

router = APIRouter()

GEMINI_VISUAL_MODEL = getattr(settings, "GEMINI_VISUAL_MODEL", "gemini-3-pro-preview")
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_VISUAL_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
)

RENDER_DPI = 450
CROP_PADDING_RATIO = 0.04
CROP_MIN_SIZE = 300
SHARPEN_ENABLED = True
OUTPUT_FORMAT = "PNG"  # ✅ çıktı formatı
OUTPUT_EXTENSION = "png"

class VisualIngestResponse(BaseModel):
    total_pages: int
    total_parts_detected: int
    total_parts_updated: int
    skipped_no_match: int
    skipped_non_technical: int

def render_page_to_image(doc: fitz.Document, page_index: int) -> Image.Image:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(dpi=RENDER_DPI, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def enhance_image(image: Image.Image) -> Image.Image:
    image = ImageOps.autocontrast(image, cutoff=1)
    if SHARPEN_ENABLED:
        image = image.filter(ImageFilter.UnsharpMask(radius=2, percent=180, threshold=3))
    return image

async def detect_parts_with_gemini(image: Image.Image) -> List[dict]:
    buffered = io.BytesIO()
    image.save(buffered, format="JPEG", quality=90, subsampling=0)
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

@router.post("/visual-ingest", response_model=VisualIngestResponse)
async def visual_ingest(
    catalog_id: str = Form(...),
    file: UploadFile = File(...),
    page_start: int = Form(1),
    page_end: int = Form(0),
    technical_pages: str = Form("[]")
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

                crop_image = crop_with_bbox(image, bbox)
                embedding_input = f"label:{label} ocr:{ocr_text} tags:{', '.join(shape_tags)}"
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
                    json.dumps(shape_tags),
                    ocr_text,
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