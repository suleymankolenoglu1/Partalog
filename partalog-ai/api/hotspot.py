"""
Hotspot API - YOLO Tespit + OCR Numara Okuma
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from loguru import logger
import time
import cv2
import numpy as np

router = APIRouter()


# ============================================
# SCHEMAS
# ============================================

class HotspotResult(BaseModel):
    """Tek bir hotspot sonucu."""
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    height: float
    center_x: float
    center_y:  float
    confidence:  float
    label:  Optional[str] = None  # OCR ile okunan numara
    
    # Normalize edilmiş koordinatlar (frontend için yüzde olarak)
    left_percent: float
    top_percent:  float
    width_percent: float
    height_percent:  float


class DetectionResponse(BaseModel):
    """API yanıt modeli."""
    success: bool
    message: str
    image_width: int
    image_height:  int
    hotspot_count: int
    labeled_count: int  # OCR ile numara okunan hotspot sayısı
    processing_time_ms:  float
    hotspots: List[HotspotResult]


# ============================================
# MODEL ACCESS
# ============================================

def get_models():
    """Ana uygulamadan model referanslarını al."""
    from main import models
    return models


# ============================================
# ENDPOINTS
# ============================================

@router.post("/detect", response_model=DetectionResponse)
async def detect_hotspots(
    file: UploadFile = File(... , description="Analiz edilecek görüntü"),
    confidence: float = Query(default=0.25, ge=0.0, le=1.0, description="Minimum güven eşiği"),
    padding: int = Query(default=5, ge=0, le=20, description="OCR için kırpma padding değeri")
):
    """
    Görüntüdeki hotspot'ları tespit eder ve içindeki numaraları okur.
    
    - **file**: Analiz edilecek görüntü dosyası (PNG, JPG, etc.)
    - **confidence**:  YOLO minimum güven eşiği (0.0-1.0)
    - **padding**: Hotspot kırpılırken eklenen kenar boşluğu
    
    Returns:
        Tespit edilen hotspot'lar ve OCR ile okunan numaralar
    """
    start_time = time. time()
    
    models = get_models()
    detector = models. get("yolo")
    ocr = models.get("ocr")
    
    if detector is None: 
        raise HTTPException(
            status_code=503, 
            detail="YOLO modeli yüklenmemiş.  models/best.pt dosyasını kontrol edin."
        )
    
    # Dosyayı oku
    try: 
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Boş dosya")
    except Exception as e: 
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {str(e)}")
    
    # YOLO ile tespit
    try: 
        detections, image = detector.detect_from_bytes(contents, confidence)
    except Exception as e:
        logger.error(f"YOLO tespit hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Tespit hatası:  {str(e)}")
    
    img_h, img_w = image.shape[:2]
    
    # Her tespit için OCR uygula
    results = []
    labeled_count = 0
    
    for det in detections: 
        label = None
        
        # OCR ile numara oku
        if ocr is not None:
            try:
                # Hotspot'u kırp
                x1 = max(0, int(det.x1) - padding)
                y1 = max(0, int(det.y1) - padding)
                x2 = min(img_w, int(det.x2) + padding)
                y2 = min(img_h, int(det.y2) + padding)
                
                crop = image[y1:y2, x1:x2]. copy()
                
                if crop.size > 0:
                    label = ocr.read_number(crop)
                    if label:
                        labeled_count += 1
                        logger.debug(f"Hotspot numara: {label} (conf: {det.confidence:.2f})")
            except Exception as e: 
                logger.warning(f"OCR hatası: {e}")
        
        # Sonuç oluştur
        results.append(HotspotResult(
            x1=round(det.x1, 2),
            y1=round(det. y1, 2),
            x2=round(det. x2, 2),
            y2=round(det. y2, 2),
            width=round(det.width, 2),
            height=round(det.height, 2),
            center_x=round(det.center[0], 2),
            center_y=round(det. center[1], 2),
            confidence=round(det.confidence, 4),
            label=label,
            left_percent=round((det.x1 / img_w) * 100, 2),
            top_percent=round((det.y1 / img_h) * 100, 2),
            width_percent=round((det.width / img_w) * 100, 2),
            height_percent=round((det.height / img_h) * 100, 2)
        ))
    
    processing_time = round((time.time() - start_time) * 1000, 2)
    
    logger.info(f"✅ {len(detections)} hotspot, {labeled_count} numara okundu ({processing_time}ms)")
    
    return DetectionResponse(
        success=True,
        message=f"{len(detections)} hotspot tespit edildi, {labeled_count} numara okundu",
        image_width=img_w,
        image_height=img_h,
        hotspot_count=len(detections),
        labeled_count=labeled_count,
        processing_time_ms=processing_time,
        hotspots=results
    )


@router.get("/info")
async def get_service_info():
    """Servis ve model bilgilerini döndürür."""
    models = get_models()
    
    info = {
        "service": "Partalog AI - Hotspot Detection",
        "models": {}
    }
    
    if models. get("yolo"):
        info["models"]["yolo"] = models["yolo"].get_info()
    
    if models.get("ocr"):
        info["models"]["ocr"] = models["ocr"].get_info()
    
    return info