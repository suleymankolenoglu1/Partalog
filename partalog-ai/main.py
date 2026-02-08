"""
Partalog AI Service - Ana Uygulama (Final v3.0 - Turkish Native & 3072 Vector)
Görevi: C# Backend için Zeka Servislerini (YOLO, OCR, Gemini, Embedding) sunmak.
"""

# --- 1. Standart Kütüphaneler ---
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger
from pydantic import BaseModel
import sys
import os
import uvicorn
import time

# --- 2. Ayarlar ---
from config import settings

# --- 3. Servisler ---
# services/embedding.py -> Senin sisteminde 3072 boyutlu vektör üretiyor.
from services.embedding import get_text_embedding 

# --- 4. API Routerları (Uç Noktalar) ---
# Buradaki api.chat modülü artık 'services.vector_db' kullanıyor (database hatası yok)
from api.hotspot import router as hotspot_router   # YOLO & OCR
from api.table import router as table_router       # Gemini Tablo Okuma
from api.analysis import router as analysis_router # Sayfa Sınıflandırma
from api.chat import router as chat_router         # Chatbot (Türkçe & 3072 Uyumlu)
from api.visual_ingest import router as visual_ingest_router  # ✅ Visual Ingest

# --- 5. Gelişmiş Loglama Ayarı ---
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)

# --- 6. Model Başlatma (Lifespan) ---
models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} (Service Mode) BAŞLATILIYOR...")
    logger.info("=" * 60)
    
    # A. YOLO Hotspot Detector Yükle (Varsa)
    if os.path.exists(settings.YOLO_MODEL_PATH):
        try:
            from core.detector import HotspotDetector
            models["yolo"] = HotspotDetector(
                settings.YOLO_MODEL_PATH, 
                settings.YOLO_CONFIDENCE, 
                settings.YOLO_IMG_SIZE
            )
            logger.success(f"✅ YOLO Modeli Yüklendi: {settings.YOLO_MODEL_PATH}")
        except Exception as e:
            logger.error(f"❌ YOLO Başlatılamadı: {e}")
    else:
        logger.warning(f"⚠️ Model dosyası yok: {settings.YOLO_MODEL_PATH}")
    
    # B. EasyOCR Yükle
    try:
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ EasyOCR Motoru Hazır.")
    except Exception as e:
        logger.error(f"❌ EasyOCR Hatası: {e}")
    
    logger.info(f"📍 Servis Yayında: http://{settings.HOST}:{settings.PORT}")
    yield
    # Kapanış
    logger.info("👋 Servis durduruluyor, modeller temizleniyor...")
    models.clear()

# --- 7. Uygulama Tanımı ---
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="C# Backend için Yardımcı Zeka Servisi (3072 Vector Edition)",
    lifespan=lifespan
)

# --- 8. CORS (Güvenlik İzinleri) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 9. Statik Dosyalar ---
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 10. Router Bağlantıları ---
app.include_router(analysis_router, prefix="/api/analysis", tags=["1. Analiz"])
app.include_router(hotspot_router, prefix="/api/hotspot", tags=["2. Hotspot (YOLO)"])
app.include_router(table_router, prefix="/api/table", tags=["3. Tablo (Gemini Türkçe)"])
app.include_router(chat_router, prefix="/api/chat", tags=["4. Chatbot"])
app.include_router(visual_ingest_router, prefix="/api", tags=["5. Visual Ingest"])

# =================================================================
# 👇 C# İÇİN YARDIMCI ENDPOINTLER
# =================================================================

class EmbeddingRequest(BaseModel):
    text: str

@app.post("/api/embed", tags=["6. Semantic Search (C# Helper)"])
async def generate_embedding_endpoint(req: EmbeddingRequest):
    """
    C# Backend bu endpoint'e metin gönderir.
    Python, Google API ile vektör döner.
    DİKKAT: Senin sisteminde bu model 3072 boyutlu çıktı veriyor.
    """
    start_time = time.time()
    if not req.text or len(req.text.strip()) < 2:
         raise HTTPException(status_code=400, detail="Metin çok kısa veya boş.")

    try:
        # services/embedding.py içindeki fonksiyonu çağır
        vector = get_text_embedding(req.text)
        
        if not vector:
             raise HTTPException(status_code=500, detail="Vektör oluşturulamadı (Google API hatası).")

        process_time = round((time.time() - start_time) * 1000, 2)
        
        # Logda boyutu görelim ki için rahat etsin (3072 bekliyoruz)
        logger.info(f"🧠 Vektör oluşturuldu ({process_time}ms) Boyut: {len(vector)}")
        
        return {"embedding": vector}

    except Exception as e:
         logger.error(f"❌ Embedding Hatası: {e}")
         raise HTTPException(status_code=500, detail=str(e))

@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "mode": "Service Mode (Native Turkish & 3072 Vector)",
        "status": "Active"
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)