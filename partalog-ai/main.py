"""
Partalog AI Service - Ana Uygulama (Final)
YOLO Hotspot Tespiti + EasyOCR Numara Okuma + Gemini Tablo Okuma + Gemini Sayfa Analizi (REST)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
import sys
import os
import uvicorn

from config import settings
from core.ai_engine import GeminiTableExtractor
from core.dependencies import set_ai_engine 

# --- ROUTER IMPORTLARI ---
# api klasöründeki routerları buraya çekiyoruz
from api.hotspot import router as hotspot_router
from api.table import router as table_router
from api.analysis import router as analysis_router 

# Logging Ayarları
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)

# Global Model Deposu (api/hotspot.py buradan erişiyor)
models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} başlatılıyor...")
    logger.info("=" * 60)
    
    # 1. YOLO Detector Yükle
    if os.path.exists(settings.YOLO_MODEL_PATH):
        try:
            from core.detector import HotspotDetector
            models["yolo"] = HotspotDetector(
                model_path=settings.YOLO_MODEL_PATH,
                confidence=settings.YOLO_CONFIDENCE,
                img_size=settings.YOLO_IMG_SIZE
            )
            logger.success(f"✅ YOLO Detector yüklendi: {settings.YOLO_MODEL_PATH}")
        except Exception as e:
            logger.error(f"❌ YOLO Hatası: {e}")
            models["yolo"] = None
    else:
        logger.warning(f"⚠️ YOLO modeli bulunamadı: {settings.YOLO_MODEL_PATH} (Hotspot tespiti çalışmayacak)")
        models["yolo"] = None
    
    # 2. EasyOCR Reader Yükle
    try:
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ EasyOCR Reader yüklendi (Numara Okuma)")
    except Exception as e:
        logger.error(f"❌ EasyOCR Başlatılamadı: {e}")
        models["ocr"] = None
    
    # 3. Gemini Table Engine (Tablo Okuyucu)
    try:
        gemini_engine = GeminiTableExtractor()
        set_ai_engine(gemini_engine) # Dependency Injection için ayarla
        models["table_reader"] = gemini_engine
        logger.success("✅ Gemini Tablo Motoru yüklendi")
    except Exception as e:
        logger.critical(f"❌ Gemini Tablo Motoru Başlatılamadı: {e}")
    
    # Not: Analysis servisi (api/analysis.py) stateless olduğu için yükleme gerektirmez.

    logger.info("=" * 60)
    logger.info("🎯 Servis hazır ve çalışıyor!")
    logger.info(f"📍 API Docs: http://localhost:{settings.PORT}/docs")
    logger.info("=" * 60)
    
    yield
    
    logger.info("👋 Servis kapatılıyor...")
    models.clear()

# FastAPI App Tanımlama
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Partalog AI - YOLO + OCR + Gemini Lite (REST)",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Statik Dosyalar (Varsa)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# --- API ROUTER BAĞLANTILARI (URL YOLLARI) ---

# 1. Page Analysis -> /api/analysis/analyze-page-title
app.include_router(analysis_router, prefix="/api/analysis", tags=["Page Analysis"])

# 2. Hotspot Detection -> /api/hotspot/detect
# 🛠️ DÜZELTME: Prefix "/api" yerine "/api/hotspot" yapıldı. 
# Böylece C#'ın beklediği adres oluştu.
app.include_router(hotspot_router, prefix="/api/hotspot", tags=["Hotspot Detection"])

# 3. Table Extraction -> /api/table/extract
app.include_router(table_router, prefix="/api/table", tags=["Table Extraction"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "Hybrid (YOLO + EasyOCR + Gemini Lite)",
        "docs": "/docs"
    }

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "models": {
            "yolo_detector": models.get("yolo") is not None,
            "easyocr": models.get("ocr") is not None,
            "table_engine": models.get("table_reader") is not None,
            "gemini_api": "Active (Stateless)"
        }
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)