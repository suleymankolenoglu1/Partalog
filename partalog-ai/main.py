"""
Partalog AI Service - Ana Uygulama (Final v2.3 - Modular Architecture)
YOLO Hotspot + OCR + Gemini Analysis + AI Chat + Embeddings (Centralized)
"""

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from pydantic import BaseModel
import sys
import os
import uvicorn

# Kendi modüllerimiz
from config import settings
from core.ai_engine import GeminiTableExtractor
from core.dependencies import set_ai_engine 
# 👇 YENİ: Embedding servisini buradan çağırıyoruz
from services.embedding import get_text_embedding

# --- ROUTER IMPORTLARI ---
from api.hotspot import router as hotspot_router
from api.table import router as table_router
from api.analysis import router as analysis_router
from api.chat import router as chat_router 

# --- EĞİTİM MODÜLÜ (Opsiyonel import) ---
try:
    import train_dictionary
except ImportError:
    logger.warning("⚠️ 'train_dictionary.py' bulunamadı. Admin eğitim endpoint'i çalışmayabilir.")
    train_dictionary = None

# Logging Ayarları
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)

# Global Model Deposu
models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} başlatılıyor...")
    logger.info("=" * 60)
    
    # 0. SÖZLÜK KONTROLÜ
    dict_path = "sanayi_sozlugu.json"
    if os.path.exists(dict_path):
        import json
        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.success(f"🧠 Sanayi Hafızası Yüklü: {len(data)} terim biliniyor.")
        except:
            logger.error("❌ Sanayi sözlüğü dosyası bozuk.")
    else:
        logger.warning("⚠️ Sanayi sözlüğü bulunamadı. '/api/admin/train' ile eğitimi başlatın.")

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
        logger.warning(f"⚠️ YOLO modeli bulunamadı: {settings.YOLO_MODEL_PATH}")
        models["yolo"] = None
    
    # 2. EasyOCR Reader Yükle
    try:
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ EasyOCR Reader yüklendi")
    except Exception as e:
        logger.error(f"❌ EasyOCR Başlatılamadı: {e}")
        models["ocr"] = None
    
    # 3. Gemini Table Engine
    try:
        gemini_engine = GeminiTableExtractor()
        set_ai_engine(gemini_engine) 
        models["table_reader"] = gemini_engine
        logger.success("✅ Gemini Tablo Motoru yüklendi")
    except Exception as e:
        logger.critical(f"❌ Gemini Tablo Motoru Başlatılamadı: {e}")
    
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
    description="Partalog AI - Complete Suite (Detection + OCR + Analysis + Chat + Embeddings)",
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

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# --- API ROUTER BAĞLANTILARI ---
app.include_router(analysis_router, prefix="/api/analysis", tags=["Page Analysis"])
app.include_router(hotspot_router, prefix="/api/hotspot", tags=["Hotspot Detection"])
app.include_router(table_router, prefix="/api/table", tags=["Table Extraction"])
app.include_router(chat_router, prefix="/api/chat", tags=["AI Chat"]) 

# --- 🔥 GÜNCELLENDİ: EMBEDDING ENDPOINT (Modüler Yapı) ---
class EmbeddingRequest(BaseModel):
    text: str

@app.post("/api/embed", tags=["Semantic Search"])
async def generate_embedding(req: EmbeddingRequest):
    """
    Metni 768 boyutlu vektöre çevirir.
    Artık 'services/embedding.py' modülünü kullanıyor.
    """
    # Tek satırda işlem bitiyor!
    vector = get_text_embedding(req.text)
    
    if not vector:
        raise HTTPException(status_code=500, detail="Vektör oluşturulamadı (Google API Hatası).")

    return {"embedding": vector}


# --- ADMIN EĞİTİM ENDPOINT'İ ---
@app.post("/api/admin/train", tags=["Admin & Training"])
async def trigger_training(background_tasks: BackgroundTasks):
    if train_dictionary:
        background_tasks.add_task(train_dictionary.main)
        return {
            "status": "started", 
            "message": "Eğitim arka planda başlatıldı."
        }
    else:
        return {"status": "error", "message": "train_dictionary.py modülü bulunamadı."}


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "features": ["YOLO", "EasyOCR", "Gemini Tables", "Embeddings", "Expert Chat"],
        "docs": "/docs"
    }

@app.get("/health", tags=["Health"])
async def health():
    dict_exists = os.path.exists("sanayi_sozlugu.json")
    return {
        "status": "healthy",
        "models": {
            "yolo_detector": models.get("yolo") is not None,
            "easyocr": models.get("ocr") is not None,
            "table_engine": models.get("table_reader") is not None,
            "embedding_service": "Active (Modular)",
            "dictionary_loaded": dict_exists
        }
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)