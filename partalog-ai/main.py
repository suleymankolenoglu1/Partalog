"""
Partalog AI Service - Ana Uygulama
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


# Model ve Servis referansları
models = {}
services = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings. APP_VERSION} başlatılıyor...")
    logger.info("=" * 60)
    
    # YOLO
    try:
        from core.detector import HotspotDetector
        models["yolo"] = HotspotDetector(
            model_path=settings.YOLO_MODEL_PATH,
            confidence=settings.YOLO_CONFIDENCE,
            img_size=settings. YOLO_IMG_SIZE
        )
        logger.success("✅ YOLO Detector yüklendi")
        from api.catalog import set_detector
        set_detector(models["yolo"])
    except Exception as e:
        logger.error(f"❌ YOLO:  {e}")
    
    # OCR
    try: 
        from core. ocr import OCRReader
        models["ocr"] = OCRReader(langs=settings.OCR_LANGS, use_gpu=settings. OCR_USE_GPU)
        logger.success("✅ OCR Reader yüklendi")
        from api. catalog import set_ocr
        set_ocr(models["ocr"])
    except Exception as e:
        logger.error(f"❌ OCR: {e}")
    
    # CLIP
    try: 
        from core.embedder import ImageEmbedder
        models["clip"] = ImageEmbedder(model_name=settings.CLIP_MODEL_NAME, pretrained=settings. CLIP_PRETRAINED)
        logger.success("✅ CLIP Embedder yüklendi")
    except Exception as e: 
        logger.error(f"❌ CLIP: {e}")
    
    # Segmenter
    try: 
        from core. segmenter import PartSegmenter
        models["segmenter"] = PartSegmenter(
            model_path=settings.SAM_MODEL_PATH,
            model_type=settings.SAM_MODEL_TYPE,
            use_sam=settings.SAM_ENABLED,
            min_area=settings. SAM_MIN_AREA
        )
        logger.success(f"✅ Part Segmenter yüklendi ({models['segmenter']. backend})")
    except Exception as e: 
        logger.error(f"❌ Segmenter: {e}")
    
    # Vector Store
    try: 
        from core.vector_store import VectorStore
        models["vector_store"] = VectorStore(
            persist_directory=str(settings.VECTOR_DB_DIR),
            collection_name=settings. VECTOR_DB_COLLECTION
        )
        logger.success("✅ Vector Store yüklendi")
    except Exception as e:
        logger.error(f"❌ Vector Store: {e}")
    
    # CatalogProcessor
    try: 
        from services.catalog_processor import CatalogProcessor
        services["processor"] = CatalogProcessor(
            detector=models. get("yolo"),
            ocr_reader=models.get("ocr"),
            segmenter=models. get("segmenter"),
            embedder=models.get("clip"),
            vector_store=models.get("vector_store")
        )
        logger.success("✅ CatalogProcessor yüklendi")
        from api.catalog import set_processor
        set_processor(services["processor"])
    except Exception as e: 
        logger.error(f"❌ CatalogProcessor:  {e}")
    
    # VisualSearchService
    try: 
        from services.visual_search import VisualSearchService
        services["search"] = VisualSearchService(
            embedder=models.get("clip"),
            vector_store=models.get("vector_store")
        )
        logger.success("✅ VisualSearchService yüklendi")
        from api.search import set_search_service, set_vector_store
        set_search_service(services["search"])
        set_vector_store(models.get("vector_store"))
    except Exception as e: 
        logger.error(f"❌ VisualSearchService: {e}")
    
    logger.info("=" * 60)
    logger.info("🎯 Servis hazır!")
    logger.info("📍 Test sayfası: http://localhost:8000/static/test.html")
    logger.info("=" * 60)
    
    yield
    
    logger.info("👋 Servis kapatılıyor...")


# FastAPI App
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Yedek parça kataloğu için AI görsel işleme servisi",
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

# Routers
from api.catalog import router as catalog_router
from api.search import router as search_router

app.include_router(catalog_router, prefix="/catalog", tags=["Catalog"])
app.include_router(search_router, prefix="/search", tags=["Search"])


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "test_page": "/static/test.html"
    }


@app. get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "models": {k: v is not None for k, v in models.items()}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)