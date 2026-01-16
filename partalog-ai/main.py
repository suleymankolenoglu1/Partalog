"""
Partalog AI Service - Ana Uygulama (Basitleştirilmiş)
Sadece YOLO Hotspot Tespiti + OCR Numara Okuma
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
import sys

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


@app. get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "models": {
            "yolo": models.get("yolo") is not None,
            "ocr":  models.get("ocr") is not None
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn. run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)