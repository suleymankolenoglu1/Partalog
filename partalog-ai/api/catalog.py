"""
Catalog API - Katalog işleme endpoint'leri
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from loguru import logger
import time
import traceback

from schemas.detection import (
    DetectionResponse,
    DetectionResult,
    NormalizedDetectionResponse,
    NormalizedDetection
)


router = APIRouter()

# Model/Servis referansları
_detector = None
_ocr = None
_processor = None


def set_detector(detector):
    global _detector
    _detector = detector


def set_ocr(ocr):
    global _ocr
    _ocr = ocr


def set_processor(processor):
    global _processor
    _processor = processor


def get_detector():
    if _detector is None: 
        raise HTTPException(status_code=503, detail="YOLO modeli yüklenmemiş.")
    return _detector


def get_ocr():
    return _ocr


# ============================================
# SCHEMAS
# ============================================

class PartInfo(BaseModel):
    id: str
    part_number:  Optional[str]
    balloon: Dict[str, Any]
    part: Optional[Dict[str, Any]]
    has_embedding: bool
    normalized: Dict[str, float]


class ProcessResponse(BaseModel):
    success: bool
    message: str
    image_width: int
    image_height: int
    processing_time_ms: float
    part_count: int
    parts: List[PartInfo]


# ============================================
# ENDPOINTS
# ============================================

@router.post(
    "/detect",
    response_model=DetectionResponse,
    summary="Hotspot Tespiti"
)
async def detect_hotspots(
    file: UploadFile = File(...),
    confidence: float = Query(default=None, ge=0.0, le=1.0),
    read_labels: bool = Query(default=True)
):
    """Sadece balloon tespiti + OCR."""
    start_time = time. time()
    
    detector = get_detector()
    ocr = get_ocr()
    
    try:
        contents = await file.read()
        detections, image = detector.detect_from_bytes(contents, confidence)
    except Exception as e: 
        logger.error(f"Tespit hatası: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    img_h, img_w = image.shape[:2]
    
    results = []
    for det in detections: 
        label = None
        if read_labels and ocr:
            try:
                crops = detector.crop_detections(image, [det], padding=5)
                if crops:
                    _, crop_img = crops[0]
                    label = ocr. read_number(crop_img)
            except: 
                pass
        
        results.append(DetectionResult(**det.to_dict(), label=label))
    
    return DetectionResponse(
        success=True,
        message=f"{len(detections)} hotspot tespit edildi",
        image_width=img_w,
        image_height=img_h,
        detection_count=len(detections),
        processing_time_ms=round((time.time() - start_time) * 1000, 2),
        detections=results
    )


@router.post(
    "/process",
    response_model=ProcessResponse,
    summary="Tam Katalog İşleme"
)
async def process_catalog_page(
    file: UploadFile = File(..., description="Teknik resim"),
    extract_embeddings: bool = Query(default=True),
    save_to_db: bool = Query(default=False),
    catalog_id: Optional[str] = Query(default=None)
):
    """Teknik resmi tam olarak işler."""
    
    if _processor is None: 
        raise HTTPException(status_code=503, detail="Processor servisi hazır değil")
    
    # Dosyayı oku
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Boş dosya")
        logger.info(f"Dosya okundu: {len(contents)} bytes")
    except Exception as e:
        logger.error(f"Dosya okuma hatası: {e}")
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {str(e)}")
    
    # İşle
    try:
        result = _processor.process_image_from_bytes(
            contents,
            extract_embeddings=extract_embeddings,
            save_to_db=save_to_db,
            catalog_id=catalog_id
        )
    except Exception as e: 
        logger.error(f"İşleme hatası:  {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"İşleme hatası: {str(e)}")
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result. message)
    
    # Response oluştur
    try:
        parts_response = []
        for p in result.parts:
            parts_response.append(PartInfo(
                id=p.id,
                part_number=p.part_number,
                balloon={
                    "bbox": p.balloon_bbox,
                    "center": p.balloon_center,
                    "confidence": p.balloon_confidence
                },
                part={
                    "bbox": p.part_bbox,
                    "centroid": p.part_centroid,
                    "area": p.part_area
                } if p.part_bbox else None,
                has_embedding=p.embedding is not None,
                normalized=p.normalized
            ))
        
        return ProcessResponse(
            success=result.success,
            message=result.message,
            image_width=result.image_width,
            image_height=result.image_height,
            processing_time_ms=result.processing_time_ms,
            part_count=len(result.parts),
            parts=parts_response
        )
    except Exception as e: 
        logger.error(f"Response oluşturma hatası: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Response hatası: {str(e)}")