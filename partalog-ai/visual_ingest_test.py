#!/usr/bin/env python3
"""
Standalone coarse-to-fine visual ingest test for technical engineering drawings.

Usage:
    python visual_ingest_test.py path/to/drawing.jpg
    python visual_ingest_test.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:
    raise SystemExit("Missing dependency: Pillow. Install with `pip install pillow`.") from exc

try:
    import google.generativeai as genai
except ImportError as exc:
    raise SystemExit(
        "Missing dependency: google-generativeai. Install with `pip install google-generativeai`."
    ) from exc

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


DEFAULT_IMAGE_NAME = "test_drawing.jpg"
DEFAULT_MODEL_NAME = "gemini-2.0-flash"
FINAL_OUTPUT_NAME = "final_result_verified.jpg"
LOG_FILE_NAME = "visual_debug.log"
MAX_CONCURRENT_API_CALLS = 3
MAX_API_RETRIES = 3

LOGGER = logging.getLogger("visual_ingest_test")


INSPECTOR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "part_number": {"type": "string"},
                    "description": {"type": "string"},
                    "local_bbox_1000": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["part_number", "description", "local_bbox_1000"],
            },
        },
    },
    "required": ["parts"],
}


VERIFIER_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"valid": {"type": "boolean"}},
    "required": ["valid"],
}


@dataclass(frozen=True)
class BBox:
    ymin: int
    xmin: int
    ymax: int
    xmax: int

    def width(self) -> int:
        return max(0, self.xmax - self.xmin)

    def height(self) -> int:
        return max(0, self.ymax - self.ymin)

    def is_valid(self, min_size: int = 1) -> bool:
        return self.width() >= min_size and self.height() >= min_size

    def clamp_to_image(self, width: int, height: int) -> "BBox":
        xmin = max(0, min(self.xmin, max(0, width - 1)))
        ymin = max(0, min(self.ymin, max(0, height - 1)))
        xmax = max(xmin + 1, min(self.xmax, width))
        ymax = max(ymin + 1, min(self.ymax, height))
        return BBox(ymin=ymin, xmin=xmin, ymax=ymax, xmax=xmax)

    def as_list(self) -> List[int]:
        return [self.ymin, self.xmin, self.ymax, self.xmax]


@dataclass(frozen=True)
class CropInfo:
    index: int
    assembly_bbox: BBox
    padded_bbox: BBox
    effective_pad_x: int
    effective_pad_y: int
    crop_path: Path


@dataclass(frozen=True)
class ValidatedPart:
    crop_index: int
    part_number: str
    description: str
    local_bbox: BBox
    global_bbox: BBox

    def to_dict(self) -> Dict[str, Any]:
        return {
            "crop_index": self.crop_index,
            "part_number": self.part_number,
            "description": self.description,
            "local_bbox": self.local_bbox.as_list(),
            "global_bbox": self.global_bbox.as_list(),
        }


class GeminiAsyncClient:
    """Async wrapper around google-generativeai with retries and JSON parsing."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        max_concurrent_calls: int = MAX_CONCURRENT_API_CALLS,
        max_retries: int = MAX_API_RETRIES,
    ) -> None:
        self.model = genai.GenerativeModel(model_name)
        self.semaphore = asyncio.Semaphore(max_concurrent_calls)
        self.max_retries = max_retries

    async def _generate_once(self, contents: Sequence[Any], generation_config: Any) -> Any:
        async with self.semaphore:
            if hasattr(self.model, "generate_content_async"):
                return await self.model.generate_content_async(
                    contents=contents, generation_config=generation_config
                )
            return await asyncio.to_thread(
                self.model.generate_content, contents=contents, generation_config=generation_config
            )

    async def generate_json(
        self,
        prompt: str,
        image: Image.Image,
        response_schema: Dict[str, Any],
        temperature: float = 0.1,
    ) -> Any:
        generation_config = genai.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=response_schema,
        )

        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._generate_once(
                    contents=[prompt, image], generation_config=generation_config
                )
                parsed = parse_response_json(response)
                if not isinstance(parsed, dict):
                    raise ValueError("Gemini returned empty or non-object JSON.")
                return parsed
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                LOGGER.warning(
                    "Gemini JSON request failed (attempt %s/%s): %s",
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(1.0 * attempt)

        raise RuntimeError(f"Gemini JSON request failed after retries: {last_error}")


def configure_logging(work_dir: Path) -> None:
    log_path = work_dir / LOG_FILE_NAME
    LOGGER.setLevel(logging.INFO)
    LOGGER.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(stream_handler)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Coarse-to-fine Gemini visual ingest test.")
    parser.add_argument(
        "image_path",
        nargs="?",
        default=DEFAULT_IMAGE_NAME,
        help=f"Path to technical drawing image (default: {DEFAULT_IMAGE_NAME})",
    )
    return parser.parse_args()


def validate_image_path(image_path_arg: str) -> Path:
    image_path = Path(image_path_arg).expanduser().resolve()
    if not image_path.exists() or not image_path.is_file():
        raise SystemExit(f"Error: image file not found -> {image_path}")
    return image_path


def setup_gemini() -> None:
    if load_dotenv is not None:
        load_dotenv()
    else:
        LOGGER.warning("python-dotenv not installed. .env file will not be auto-loaded.")

    api_key = os.getenv("GOOGLE_API_KEY", "YOUR_GOOGLE_API_KEY")
    if not api_key or api_key == "YOUR_GOOGLE_API_KEY":
        raise SystemExit(
            "Error: GOOGLE_API_KEY is missing. Define it in environment or .env file."
        )
    genai.configure(api_key=api_key)


def extract_response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text)

    candidates = getattr(response, "candidates", None)
    if not candidates:
        return ""

    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) if content else None
        if not parts:
            continue
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                return str(part_text)
    return ""


def parse_response_json(response: Any) -> Optional[Any]:
    if hasattr(response, "parsed"):
        parsed = getattr(response, "parsed")
        if parsed is not None:
            return parsed

    raw_text = extract_response_text(response).strip()
    if not raw_text:
        return None

    candidates = [raw_text]
    fenced_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL | re.IGNORECASE)
    if fenced_match:
        candidates.append(fenced_match.group(1).strip())

    obj_match = re.search(r"(\{[\s\S]*\})", raw_text)
    if obj_match:
        candidates.append(obj_match.group(1).strip())

    seen = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def normalize_1000_to_pixel(
    bbox_1000: Any,
    width: int,
    height: int,
) -> Optional[BBox]:
    """Strict conversion from 0-1000 coordinate space to pixel space."""
    if not isinstance(bbox_1000, (list, tuple)) or len(bbox_1000) != 4:
        return None

    try:
        y1_1000, x1_1000, y2_1000, x2_1000 = [float(v) for v in bbox_1000]
    except (TypeError, ValueError):
        return None

    y1_1000 = max(0.0, min(1000.0, y1_1000))
    x1_1000 = max(0.0, min(1000.0, x1_1000))
    y2_1000 = max(0.0, min(1000.0, y2_1000))
    x2_1000 = max(0.0, min(1000.0, x2_1000))

    y_min_1000, y_max_1000 = sorted([y1_1000, y2_1000])
    x_min_1000, x_max_1000 = sorted([x1_1000, x2_1000])

    y_min_px = int(math.floor((y_min_1000 / 1000.0) * height))
    x_min_px = int(math.floor((x_min_1000 / 1000.0) * width))
    y_max_px = int(math.ceil((y_max_1000 / 1000.0) * height))
    x_max_px = int(math.ceil((x_max_1000 / 1000.0) * width))

    bbox = BBox(
        ymin=y_min_px,
        xmin=x_min_px,
        ymax=y_max_px,
        xmax=x_max_px,
    ).clamp_to_image(width, height)
    return bbox if bbox.is_valid() else None


def bbox_area(bbox: BBox) -> int:
    return bbox.width() * bbox.height()


def bbox_iou(a: BBox, b: BBox) -> float:
    inter_xmin = max(a.xmin, b.xmin)
    inter_ymin = max(a.ymin, b.ymin)
    inter_xmax = min(a.xmax, b.xmax)
    inter_ymax = min(a.ymax, b.ymax)

    inter_w = max(0, inter_xmax - inter_xmin)
    inter_h = max(0, inter_ymax - inter_ymin)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    union_area = bbox_area(a) + bbox_area(b) - inter_area
    if union_area <= 0:
        return 0.0
    return inter_area / union_area


def deduplicate_parts(parts_list: List[ValidatedPart], iou_threshold: float = 0.3) -> List[ValidatedPart]:
    """
    Deduplicate detections by part_number using IoU suppression.
    For overlapping duplicates (IoU > threshold), keeps the larger-area box.
    """
    grouped: Dict[str, List[ValidatedPart]] = {}
    for part in sorted(parts_list, key=lambda p: p.part_number):
        grouped.setdefault(part.part_number, []).append(part)

    deduped: List[ValidatedPart] = []
    for part_number in sorted(grouped.keys()):
        group = grouped[part_number]
        sorted_group = sorted(group, key=lambda p: bbox_area(p.global_bbox), reverse=True)
        kept: List[ValidatedPart] = []
        for candidate in sorted_group:
            duplicate = any(bbox_iou(candidate.global_bbox, existing.global_bbox) > iou_threshold for existing in kept)
            if not duplicate:
                kept.append(candidate)

        LOGGER.info(
            "Dedup group part_number=%s: before=%s after=%s",
            part_number,
            len(group),
            len(kept),
        )
        deduped.extend(kept)

    deduped.sort(key=lambda p: (p.part_number, p.global_bbox.ymin, p.global_bbox.xmin))
    return deduped


def generate_sliding_windows(
    image_width: int,
    image_height: int,
    cols: int = 4,
    rows: int = 3,
    overlap: float = 0.20,
) -> List[BBox]:
    """
    Deterministically tile the image into a fixed grid with overlap.
    Default config: 4 columns x 3 rows with 20% overlap on adjacent windows.
    """
    if cols <= 0 or rows <= 0:
        raise ValueError("Grid dimensions must be positive.")

    cell_w = int(math.ceil(image_width / cols))
    cell_h = int(math.ceil(image_height / rows))
    ov_w = int(round(cell_w * overlap))
    ov_h = int(round(cell_h * overlap))

    windows: List[BBox] = []
    for row in range(rows):
        for col in range(cols):
            x0 = col * cell_w - (ov_w if col > 0 else 0)
            y0 = row * cell_h - (ov_h if row > 0 else 0)
            x1 = (col + 1) * cell_w + (ov_w if col < cols - 1 else 0)
            y1 = (row + 1) * cell_h + (ov_h if row < rows - 1 else 0)

            bbox = BBox(ymin=y0, xmin=x0, ymax=y1, xmax=x1).clamp_to_image(image_width, image_height)
            if bbox.is_valid():
                windows.append(bbox)

    return windows


def stage2_cropper(full_image: Image.Image, regions: List[BBox], source_image_path: Path) -> List[CropInfo]:
    crops: List[CropInfo] = []
    for idx, region in enumerate(regions):
        pad_x = max(1, int(round(region.width() * 0.10)))
        pad_y = max(1, int(round(region.height() * 0.10)))

        padded = BBox(
            ymin=region.ymin - pad_y,
            xmin=region.xmin - pad_x,
            ymax=region.ymax + pad_y,
            xmax=region.xmax + pad_x,
        ).clamp_to_image(full_image.width, full_image.height)

        effective_pad_x = region.xmin - padded.xmin
        effective_pad_y = region.ymin - padded.ymin

        crop_img = full_image.crop((padded.xmin, padded.ymin, padded.xmax, padded.ymax))
        crop_path = source_image_path.parent / f"temp_crop_{idx}.jpg"
        crop_img.save(crop_path, format="JPEG", quality=95)

        LOGGER.info(
            "Stage 2 crop %s saved: %s | region=%s | padded=%s",
            idx,
            crop_path.name,
            region.as_list(),
            padded.as_list(),
        )

        crops.append(
            CropInfo(
                index=idx,
                assembly_bbox=region,
                padded_bbox=padded,
                effective_pad_x=effective_pad_x,
                effective_pad_y=effective_pad_y,
                crop_path=crop_path,
            )
        )
    return crops


def draw_red_box_mark(crop_image: Image.Image, bbox: BBox) -> Image.Image:
    marked = crop_image.copy()
    draw = ImageDraw.Draw(marked)
    thickness = max(4, int(round(min(marked.width, marked.height) * 0.01)))
    draw.rectangle(
        (bbox.xmin, bbox.ymin, max(bbox.xmin + 1, bbox.xmax - 1), max(bbox.ymin + 1, bbox.ymax - 1)),
        outline=(255, 0, 0),
        width=thickness,
    )
    return marked


def parse_bool(data: Any) -> bool:
    if isinstance(data, bool):
        return data
    if isinstance(data, dict):
        val = data.get("valid")
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() == "true"
    if isinstance(data, str):
        return data.strip().lower() == "true"
    return False


def map_local_to_global(
    crop: CropInfo,
    local_bbox: BBox,
    full_width: int,
    full_height: int,
) -> BBox:
    # Stage 5 formula basis:
    # Global_X = Crop_Origin_X + Local_X - Padding
    gxmin = crop.assembly_bbox.xmin + local_bbox.xmin - crop.effective_pad_x
    gxmax = crop.assembly_bbox.xmin + local_bbox.xmax - crop.effective_pad_x
    gymin = crop.assembly_bbox.ymin + local_bbox.ymin - crop.effective_pad_y
    gymax = crop.assembly_bbox.ymin + local_bbox.ymax - crop.effective_pad_y
    return BBox(ymin=gymin, xmin=gxmin, ymax=gymax, xmax=gxmax).clamp_to_image(
        full_width, full_height
    )


async def verify_part_with_red_box(
    client: GeminiAsyncClient,
    crop_image: Image.Image,
    crop_info: CropInfo,
    part_number: str,
    description: str,
    local_bbox: BBox,
    full_width: int,
    full_height: int,
) -> Optional[ValidatedPart]:
    marked_image = draw_red_box_mark(crop_image, local_bbox)
    prompt = (
        f"Verify if the part inside the red box is indeed part number '{part_number}'. "
        "Answer strictly boolean: true/false."
    )

    try:
        verify_data = await client.generate_json(prompt, marked_image, VERIFIER_SCHEMA, temperature=0.0)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning(
            "Stage 4 verification request failed for crop=%s part=%s: %s",
            crop_info.index,
            part_number,
            exc,
        )
        return None

    if not parse_bool(verify_data):
        LOGGER.info("Stage 4 rejected part: crop=%s part=%s", crop_info.index, part_number)
        return None

    global_bbox = map_local_to_global(crop_info, local_bbox, full_width, full_height)
    return ValidatedPart(
        crop_index=crop_info.index,
        part_number=part_number,
        description=description,
        local_bbox=local_bbox,
        global_bbox=global_bbox,
    )


async def stage3_and_4_process_crop(
    client: GeminiAsyncClient,
    crop_info: CropInfo,
    full_width: int,
    full_height: int,
) -> List[ValidatedPart]:
    with Image.open(crop_info.crop_path) as img:
        crop_image = img.convert("RGB")

    prompt = (
        "SYSTEM: You are a precision part detector for technical drawings.\n"
        "This is a section of a larger technical drawing. Find ALL numbered parts. Do not miss any labels.\n"
        "Draw a bounding box that FULLY ENCOMPASSES the part number label and the immediate area of the part it "
        "points to. Ensure the entire label is visible.\n"
        "Coordinate protocol is strict: coordinates MUST be on a 0-1000 integer scale "
        "(where 1000 represents full crop width/height).\n"
        "Return JSON only under key `parts`.\n"
        "Each part must include:\n"
        "- part_number (string)\n"
        "- description (string)\n"
        "- local_bbox_1000 as [ymin, xmin, ymax, xmax]"
    )

    try:
        data = await client.generate_json(prompt, crop_image, INSPECTOR_SCHEMA, temperature=0.1)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Stage 3 failed for crop=%s: %s", crop_info.index, exc)
        return []

    raw_parts = data.get("parts", [])
    if not isinstance(raw_parts, list):
        LOGGER.warning("Stage 3 returned invalid parts payload for crop=%s", crop_info.index)
        return []

    parsed_parts: List[Dict[str, Any]] = []
    for item in raw_parts:
        if not isinstance(item, dict):
            continue

        part_number = str(item.get("part_number", "")).strip()
        description = str(item.get("description", "")).strip()
        local_bbox = normalize_1000_to_pixel(
            item.get("local_bbox_1000"),
            width=crop_image.width,
            height=crop_image.height,
        )
        if not part_number or local_bbox is None:
            continue

        parsed_parts.append(
            {
                "part_number": part_number,
                "description": description,
                "local_bbox": local_bbox,
            }
        )

    LOGGER.info(
        "Stage 3 parsed %s candidate parts from crop=%s",
        len(parsed_parts),
        crop_info.index,
    )

    verify_tasks = [
        verify_part_with_red_box(
            client=client,
            crop_image=crop_image,
            crop_info=crop_info,
            part_number=part["part_number"],
            description=part["description"],
            local_bbox=part["local_bbox"],
            full_width=full_width,
            full_height=full_height,
        )
        for part in parsed_parts
    ]

    verify_results = await asyncio.gather(*verify_tasks, return_exceptions=True)
    validated: List[ValidatedPart] = []
    for result in verify_results:
        if isinstance(result, Exception):
            LOGGER.warning("Stage 4 part verification crashed for crop=%s: %s", crop_info.index, result)
            continue
        if result is not None:
            validated.append(result)

    LOGGER.info("Stage 4 accepted %s parts from crop=%s", len(validated), crop_info.index)
    return validated


def stage6_render_final_proof(source_image_path: Path, validated_parts: List[ValidatedPart]) -> Path:
    with Image.open(source_image_path) as img:
        canvas = img.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    for part in validated_parts:
        bbox = part.global_bbox
        draw.rectangle(
            (bbox.xmin, bbox.ymin, max(bbox.xmin + 1, bbox.xmax - 1), max(bbox.ymin + 1, bbox.ymax - 1)),
            outline=(0, 200, 0),
            width=3,
        )

        text_x = bbox.xmin
        text_y = max(0, bbox.ymin - 12)
        label = part.part_number
        try:
            text_rect = draw.textbbox((text_x, text_y), label, font=font)
        except AttributeError:
            text_rect = None
        if text_rect:
            draw.rectangle(text_rect, fill=(0, 0, 0))
        draw.text((text_x, text_y), label, fill=(0, 255, 0), font=font)

    output_path = source_image_path.parent / FINAL_OUTPUT_NAME
    canvas.save(output_path, format="JPEG", quality=95)
    return output_path


def sanitize_part_filename(part_number: str) -> str:
    sanitized = part_number.replace("/", "_")
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", sanitized)
    sanitized = sanitized.strip("._")
    return sanitized or "part"

def save_individual_crops(source_image_path: Path, validated_parts: List[ValidatedPart]) -> List[Path]:
    output_dir = Path(__file__).resolve().parent / "extracted_parts"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # --- YENİ AYARLAR ---
    # EXPANSION_FACTOR: Kutuyu ne kadar büyüteceğiz?
    # 0.5 = %50 büyüt (Biraz daha geniş)
    # 1.0 = %100 büyüt (Boyutunu ikiye katla - Agresif)
    # 1.5 = %150 büyüt (Çok agresif, büyük parçalar için iyi)
    EXPANSION_FACTOR = 1.2  # %120 büyütmeyi deneyelim, iyi bir denge olabilir.

    MIN_CROP_DIM = 50  # Kutu büyüdüğü için çöp filtresini de büyüttük.

    base_counts: Dict[str, int] = {}
    for part in validated_parts:
        base = sanitize_part_filename(part.part_number)
        base_counts[base] = base_counts.get(base, 0) + 1
        
    running_index: Dict[str, int] = {}
    saved_paths: List[Path] = []
    
    with Image.open(source_image_path) as img:
        full_img = img.convert("RGB")
        img_width, img_height = full_img.size
        
        for part in validated_parts:
            base = sanitize_part_filename(part.part_number)
            running_index[base] = running_index.get(base, 0) + 1
            
            if base_counts[base] > 1:
                filename = f"{base}_{running_index[base]}.jpg"
            else:
                filename = f"{base}.jpg"
            
            # --- AGRESİF GENİŞLETME MANTIĞI ---
            bbox = part.global_bbox
            center_x = (bbox.xmin + bbox.xmax) / 2.0
            center_y = (bbox.ymin + bbox.ymax) / 2.0
            current_width = bbox.width()
            current_height = bbox.height()

            new_width = current_width * (1 + EXPANSION_FACTOR)
            new_height = current_height * (1 + EXPANSION_FACTOR)

            new_xmin = int(center_x - (new_width / 2.0))
            new_ymin = int(center_y - (new_height / 2.0))
            new_xmax = int(center_x + (new_width / 2.0))
            new_ymax = int(center_y + (new_height / 2.0))

            expanded_bbox = BBox(
                ymin=new_ymin,
                xmin=new_xmin,
                ymax=new_ymax,
                xmax=new_xmax,
            ).clamp_to_image(img_width, img_height)
            # ------------------------------------
            
            # GARBAGE FILTER check
            if expanded_bbox.width() < MIN_CROP_DIM or expanded_bbox.height() < MIN_CROP_DIM:
                LOGGER.info("Skipping garbage crop (too small): %s", filename)
                continue
            
            crop = full_img.crop((expanded_bbox.xmin, expanded_bbox.ymin, expanded_bbox.xmax, expanded_bbox.ymax))
            save_path = output_dir / filename
            crop.save(save_path, format="JPEG", quality=95)
            saved_paths.append(save_path)
            
    return saved_paths


async def run_pipeline(image_path: Path) -> None:
    setup_gemini()
    client = GeminiAsyncClient(model_name=DEFAULT_MODEL_NAME)
    extracted_dir = Path(__file__).resolve().parent / "extracted_parts"
    extracted_dir.mkdir(parents=True, exist_ok=True)

    with Image.open(image_path) as img:
        full_image = img.convert("RGB")

    LOGGER.info("Pipeline started: %s", image_path)

    LOGGER.info("Stage 1: Deterministic Sliding Window Generator")
    regions = generate_sliding_windows(
        image_width=full_image.width,
        image_height=full_image.height,
        cols=4,
        rows=3,
        overlap=0.20,
    )
    LOGGER.info("Stage 1 complete. Window count: %s", len(regions))

    LOGGER.info("Stage 2: Cropper")
    crops = stage2_cropper(full_image, regions, image_path)
    LOGGER.info("Stage 2 complete. Crop count: %s", len(crops))

    LOGGER.info("Stage 3+4: Inspector + Visual Verifier (async)")
    crop_tasks = [
        stage3_and_4_process_crop(client, crop_info, full_image.width, full_image.height)
        for crop_info in crops
    ]
    crop_results = await asyncio.gather(*crop_tasks, return_exceptions=True)

    validated_parts: List[ValidatedPart] = []
    for result in crop_results:
        if isinstance(result, Exception):
            LOGGER.warning("A crop task failed: %s", result)
            continue
        validated_parts.extend(result)
    LOGGER.info("Stage 3+4 complete. Validated total: %s", len(validated_parts))

    LOGGER.info("Stage 5.5: Deduplication / NMS")
    before_dedup = len(validated_parts)
    validated_parts = deduplicate_parts(validated_parts, iou_threshold=0.3)
    LOGGER.info("Stage 5.5 complete. Before=%s After=%s", before_dedup, len(validated_parts))

    LOGGER.info("Stage 6: Final visualization")
    output_path = stage6_render_final_proof(image_path, validated_parts)

    payload = {
        "image_path": str(image_path),
        "model": DEFAULT_MODEL_NAME,
        "validated_count": len(validated_parts),
        "parts": [part.to_dict() for part in validated_parts],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("✅ Visual proof saved to final_result_verified.jpg")

    saved_crops = save_individual_crops(image_path, validated_parts)
    LOGGER.info(
        "Saved %s individual part crops to %s",
        len(saved_crops),
        extracted_dir,
    )

    LOGGER.info("Pipeline finished. Final image: %s", output_path)
    LOGGER.info("Detailed logs written to: %s", image_path.parent / LOG_FILE_NAME)


def main() -> None:
    args = parse_args()
    image_path = validate_image_path(args.image_path)
    configure_logging(image_path.parent)

    try:
        asyncio.run(run_pipeline(image_path))
    except KeyboardInterrupt:
        raise SystemExit("Interrupted by user.") from None


if __name__ == "__main__":
    main()
