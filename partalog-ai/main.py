"""
Partalog AI Service - Ana Uygulama (Basitleştirilmiş)
Sadece YOLO Hotspot Tespiti + OCR Numara Okuma
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from typing import List, Optional
from pydantic import BaseModel
import sys
import time

from config import settings


# Logging
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time: YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>: <cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)


# Model referansları
models = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} başlatılıyor...")
    logger.info("=" * 60)
    
    # YOLO Detector
    try:
        from core.detector import HotspotDetector
        models["yolo"] = HotspotDetector(
            model_path=settings. YOLO_MODEL_PATH,
            confidence=settings. YOLO_CONFIDENCE,
            img_size=settings. YOLO_IMG_SIZE
        )
        logger.success("✅ YOLO Detector yüklendi")
    except Exception as e:
        logger.error(f"❌ YOLO:  {e}")
        models["yolo"] = None
    
    # OCR Reader
    try: 
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ OCR Reader yüklendi")
    except Exception as e:
        logger.error(f"❌ OCR: {e}")
        models["ocr"] = None
    
    logger.info("=" * 60)
    logger.info("🎯 Servis hazır!")
    logger.info(f"📍 API Docs: http://localhost:{settings.PORT}/docs")
    logger.info(f"📍 Test Page: http://localhost:{settings.PORT}/static/test.html")
    logger.info("=" * 60)
    
    yield
    
    logger.info("👋 Servis kapatılıyor...")


# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Yedek parça kataloğu için AI görsel işleme servisi - YOLO + OCR",
    lifespan=lifespan
)

# CORS
app. add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# API Router
from api.hotspot import router as hotspot_router
app.include_router(hotspot_router, prefix="/api", tags=["Hotspot Detection"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "test_page": "/static/test.html",
        "endpoints": {
            "detect": "/api/detect - Hotspot tespit + OCR numara okuma",
            "info": "/api/info - Servis bilgileri"
        }
    }


@app.get("/health", tags=["Health"])
async def health():
    """Backend-compatible health check endpoint."""
    yolo_loaded = models.get("yolo") is not None
    ocr_loaded = models.get("ocr") is not None
    
    return {
        "status": "healthy" if yolo_loaded else "degraded",
        "modelLoaded": yolo_loaded,
        "modelPath": settings.YOLO_MODEL_PATH if yolo_loaded else None,
        "ocrLoaded": ocr_loaded
    }


# Backend-compatible /detect endpoint (without /api prefix)


class BackendCompatibleDetection(BaseModel):
    """Backend-compatible detection result."""
    left: float
    top: float
    width: float
    height: float
    confidence: float
    label: Optional[str] = None


class BackendCompatibleResponse(BaseModel):
    """Backend-compatible API response."""
    success: bool
    message: str
    filename: str
    imageWidth: int
    imageHeight: int
    detectionCount: int
    processingTimeMs: float
    detections: List[BackendCompatibleDetection]
    error: Optional[str] = None


@app.post("/detect", response_model=BackendCompatibleResponse, tags=["Backend Compatible"])
async def backend_detect(
    file: UploadFile = File(..., description="Image file to analyze"),
    min_confidence: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimum confidence threshold")
):
    """
    Backend-compatible hotspot detection endpoint.
    
    This endpoint returns data in the format expected by the .NET backend (YoloService.cs).
    Query parameter uses 'min_confidence' (with underscore) to match backend expectations.
    """
    start_time = time.time()
    
    detector = models.get("yolo")
    ocr = models.get("ocr")
    
    if detector is None:
        return BackendCompatibleResponse(
            success=False,
            message="YOLO model not loaded",
            filename=file.filename or "unknown",
            imageWidth=0,
            imageHeight=0,
            detectionCount=0,
            processingTimeMs=0.0,
            detections=[],
            error="YOLO model not loaded. Check models/best.pt file."
        )
    
    # Read file
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Empty file")
    except Exception as e:
        return BackendCompatibleResponse(
            success=False,
            message="Failed to read file",
            filename=file.filename or "unknown",
            imageWidth=0,
            imageHeight=0,
            detectionCount=0,
            processingTimeMs=0.0,
            detections=[],
            error=f"File read error: {str(e)}"
        )
    
    # YOLO detection
    try:
        detections, image = detector.detect_from_bytes(contents, min_confidence)
    except Exception as e:
        logger.error(f"YOLO detection error: {e}")
        return BackendCompatibleResponse(
            success=False,
            message="Detection failed",
            filename=file.filename or "unknown",
            imageWidth=0,
            imageHeight=0,
            detectionCount=0,
            processingTimeMs=0.0,
            detections=[],
            error=f"Detection error: {str(e)}"
        )
    
    img_h, img_w = image.shape[:2]
    
    # Convert detections to backend format
    backend_detections = []
    for det in detections:
        # Calculate percentage-based coordinates (backend expects percentages)
        left_percent = (det.x1 / img_w) * 100
        top_percent = (det.y1 / img_h) * 100
        width_percent = (det.width / img_w) * 100
        height_percent = (det.height / img_h) * 100
        
        # Try OCR if available
        label = None
        if ocr is not None:
            try:
                padding = 5
                x1 = max(0, int(det.x1) - padding)
                y1 = max(0, int(det.y1) - padding)
                x2 = min(img_w, int(det.x2) + padding)
                y2 = min(img_h, int(det.y2) + padding)
                crop = image[y1:y2, x1:x2].copy()
                
                if crop.size > 0:
                    label = ocr.read_number(crop)
            except Exception as e:
                logger.warning(f"OCR error: {e}")
        
        backend_detections.append(BackendCompatibleDetection(
            left=round(left_percent, 2),
            top=round(top_percent, 2),
            width=round(width_percent, 2),
            height=round(height_percent, 2),
            confidence=round(det.confidence, 4),
            label=label
        ))
    
    processing_time = round((time.time() - start_time) * 1000, 2)
    
    logger.info(f"✅ Backend-compatible: {len(detections)} hotspots detected ({processing_time}ms)")
    
    return BackendCompatibleResponse(
        success=True,
        message=f"{len(detections)} hotspot(s) detected",
        filename=file.filename or "unknown",
        imageWidth=img_w,
        imageHeight=img_h,
        detectionCount=len(detections),
        processingTimeMs=processing_time,
        detections=backend_detections
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)