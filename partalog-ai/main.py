"""
Partalog AI Service - Ana Uygulama (Final v2.4 - Service Mode)
Görevi: C# Backend için Zeka Servislerini (YOLO, OCR, Gemini, Embedding) sunmak.
"""

# --- 1. Standart Kütüphaneler ---
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
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

# --- 3. Çekirdek Yapay Zeka Modülleri ---
from core.ai_engine import GeminiTableExtractor
from core.dependencies import set_ai_engine 
from services.embedding import get_text_embedding # 🧠 C# için Vektör Servisi

# --- 4. API Routerları (Uç Noktalar) ---
from api.hotspot import router as hotspot_router  # YOLO & OCR
from api.table import router as table_router      # Gemini Tablo Okuma
from api.analysis import router as analysis_router # Sayfa Sınıflandırma
from api.chat import router as chat_router        # Chatbot (Veritabanı Okur)

# --- 5. Eğitim Modülü (Hata Önleyici ile) ---
try:
    import train_dictionary
except ImportError:
    logger.warning("⚠️ 'train_dictionary.py' bulunamadı veya hatalı. Eğitim çalışmayabilir.")
    train_dictionary = None

# --- 6. Gelişmiş Loglama Ayarı ---
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.DEBUG else "INFO",
    colorize=True
)

# --- 7. Model Başlatma (Lifespan) ---
# Uygulama açılırken modelleri yükler, kapanırken temizler.
models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} (Service Mode) BAŞLATILIYOR...")
    logger.info("=" * 60)
    
    # A. Sözlük Kontrolü
    if os.path.exists("sanayi_sozlugu.json"):
        logger.success("🧠 Sanayi Hafızası (Sözlük) yüklü.")
    else:
        logger.warning("⚠️ Sanayi sözlüğü henüz yok. C# ilk kataloğu yükleyince oluşacak.")

    # B. YOLO Hotspot Detector Yükle
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
    
    # C. EasyOCR Yükle
    try:
        from core.ocr import HotspotOCR
        models["ocr"] = HotspotOCR(use_gpu=settings.OCR_USE_GPU)
        logger.success("✅ EasyOCR Motoru Hazır.")
    except Exception as e:
        logger.error(f"❌ EasyOCR Hatası: {e}")
    
    # D. Gemini Motorunu Hazırla
    try:
        gemini_engine = GeminiTableExtractor()
        set_ai_engine(gemini_engine) 
        logger.success("✅ Gemini AI Motoru Bağlandı.")
    except Exception as e:
        logger.critical(f"❌ Gemini Bağlantı Hatası: {e}")
    
    logger.info(f"📍 Servis Yayında: http://{settings.HOST}:{settings.PORT}")
    yield
    # Kapanış
    logger.info("👋 Servis durduruluyor, modeller temizleniyor...")
    models.clear()

# --- 8. Uygulama Tanımı ---
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="C# Backend için Yardımcı Zeka Servisi",
    lifespan=lifespan
)

# --- 9. CORS (Güvenlik İzinleri) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Geliştirme ortamı için herkese izin ver
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 10. Statik Dosyalar ---
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 11. Router Bağlantıları ---
app.include_router(analysis_router, prefix="/api/analysis", tags=["1. Analiz"])
app.include_router(hotspot_router, prefix="/api/hotspot", tags=["2. Hotspot (YOLO)"])
app.include_router(table_router, prefix="/api/table", tags=["3. Tablo (Gemini)"])
app.include_router(chat_router, prefix="/api/chat", tags=["4. Chatbot"])

# =================================================================
# 👇 KRİTİK ENDPOINTLER (C# BURALARLA KONUŞACAK)
# =================================================================

# Model: Embedding İsteği
class EmbeddingRequest(BaseModel):
    text: str

@app.post("/api/embed", tags=["5. Semantic Search (C# Helper)"])
async def generate_embedding(req: EmbeddingRequest):
    """
    C# Backend bu endpoint'e metin gönderir (örn: "Solenoid Valf").
    Python, Google API'yi kullanarak bunu 768 boyutlu vektöre çevirir.
    """
    start = time.time()
    if not req.text or len(req.text.strip()) < 2:
         raise HTTPException(status_code=400, detail="Metin çok kısa veya boş.")

    # Servis dosyasını çağır
    vector = get_text_embedding(req.text)
    
    if not vector:
        raise HTTPException(status_code=500, detail="Google API'den vektör alınamadı.")

    process_time = round((time.time() - start) * 1000, 2)
    logger.info(f"🧠 Vektör oluşturuldu ({process_time}ms): {req.text[:30]}...")
    
    return {"embedding": vector}


@app.post("/api/admin/train", tags=["6. Admin & Training"])
async def trigger_training(background_tasks: BackgroundTasks):
    """
    C# veritabanına kaydı bitirince burayı tetikler.
    Bu kod arka planda 'train_dictionary.py' dosyasını çalıştırır.
    """
    if train_dictionary:
        # Arka planda çalıştır (Fire-and-Forget)
        background_tasks.add_task(train_dictionary.main)
        logger.info("🚂 C#'tan eğitim emri geldi. Eğitim başlatılıyor...")
        return {"status": "started", "message": "Sözlük eğitimi başlatıldı."}
    else:
        logger.error("❌ Eğitim modülü yüklenemediği için işlem yapılamadı.")
        raise HTTPException(status_code=503, detail="Eğitim modülü (train_dictionary) bulunamadı.")

# =================================================================

@app.get("/", tags=["Health"])
async def root():
    return {
        "service": settings.APP_NAME,
        "mode": "Service Mode (Connected to C#)",
        "status": "Active"
    }

# Doğrudan çalıştırma desteği
if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)