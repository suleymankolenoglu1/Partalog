"""
Partalog AI Service - Ana Uygulama (Final Fix)
YOLO Hotspot Tespiti + EasyOCR Numara Okuma + Gemini 1.5 Flash Tablo Okuma
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
import sys

from config import settings
# Yeni importlar:
from core.ai_engine import GeminiTableExtractor
from core.dependencies import set_ai_engine # <-- Dependency Setter

# Logging Ayarları
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)

# Model referanslarını tutacağımız global sözlük (YOLO ve OCR için)
models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} başlatılıyor...")
    logger.info("=" * 60)
    
    # 1. YOLO Detector
    try:
        from core.detector import HotspotDetector
        models["yolo"] = HotspotDetector(
            model_path=settings.YOLO_MODEL_PATH,
            confidence=settings.YOLO_CONFIDENCE,
            img_size=settings.YOLO_IMG_SIZE
        )
        logger.success("✅ YOLO Detector yüklendi (Hotspot)")
    except Exception as e:
        logger.error(f"❌ YOLO Başlatılamadı: {e}")
        models["yolo"] = None
    
    # 2. EasyOCR Reader
    try:
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ EasyOCR Reader yüklendi (Numara Okuma)")
    except Exception as e:
        logger.error(f"❌ EasyOCR Başlatılamadı: {e}")
        models["ocr"] = None
    
    # 3. Gemini AI Engine (ÖNEMLİ DEĞİŞİKLİK BURADA)
    try:
        # Motoru başlat
        gemini_engine = GeminiTableExtractor()
        
        # Dependency sistemine kaydet (Böylece api/table.py buna ulaşabilir)
        set_ai_engine(gemini_engine)
        
        # İstersen models sözlüğünde de tutabilirsin (opsiyonel)
        models["table_reader"] = gemini_engine
        
        logger.success("✅ Gemini 1.5 Flash Motoru yüklendi ve Dependency'e atandı.")
    except Exception as e:
        logger.critical(f"❌ Gemini AI Motoru Başlatılamadı: {e}")
        # Hata olsa bile None olarak set etmeyelim, raise etsin ki görelim
    
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
    description="Partalog AI - YOLO + EasyOCR + Gemini 1.5 Flash",
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

# Statik Dosyalar
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception:
    pass

# API Router'ları Dahil Etme
# Artık döngüsel import hatası vermeyecek çünkü main.py -> api -> main.py zinciri kırıldı.
from api.hotspot import router as hotspot_router
from api.table import router as table_router

app.include_router(hotspot_router, prefix="/api", tags=["Hotspot Detection"])
app.include_router(table_router, prefix="/api/table", tags=["Table Extraction"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "mode": "Hybrid (Local YOLO + Cloud Gemini)",
        "docs": "/docs"
    }

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "models": {
            "yolo_detector": models.get("yolo") is not None,
            "easyocr": models.get("ocr") is not None,
            "gemini_ai": models.get("table_reader") is not None
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)