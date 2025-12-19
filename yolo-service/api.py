"""
YOLO Hotspot Detection API
Katalogcu projesi için hotspot tespit servisi
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from ultralytics import YOLO
import cv2
import numpy as np
import time
import os

# ============================================================================
# MODELLER (Response/Request)
# ============================================================================

class HotspotDetection(BaseModel):
    """Tek bir hotspot tespiti - . NET Hotspot Entity ile uyumlu"""
    left:  float       # X koordinatı (% cinsinden, 0-100)
    top: float        # Y koordinatı (% cinsinden, 0-100)
    width: float      # Genişlik (% cinsinden)
    height: float     # Yükseklik (% cinsinden)
    confidence: float # AI güven skoru (0-1)
    label: Optional[str] = None  # Numara (YOLO okuyamaz, sonra OCR ile doldurulur)


class DetectionResponse(BaseModel):
    """API Response modeli"""
    success: bool
    message: str
    filename: str
    image_width: int
    image_height: int
    detection_count: int
    processing_time_ms: float
    detections: List[HotspotDetection]
    error: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    model_loaded: bool
    model_path: str


# ============================================================================
# FASTAPI UYGULAMASI
# ============================================================================

app = FastAPI(
    title="YOLO Hotspot Detection API",
    description="Katalogcu projesi için teknik çizimlerde hotspot tespiti",
    version="1.0.0"
)

# CORS - . NET backend'in erişebilmesi için
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da bunu kısıtla
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# MODEL YÜKLEME
# ============================================================================

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "best. pt")
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.5"))

print("=" * 60)
print("🚀 YOLO Hotspot Detection API Başlatılıyor...")
print(f"📦 Model: {MODEL_PATH}")
print(f"🎯 Min Confidence: {MIN_CONFIDENCE}")
print("=" * 60)

try:
    model = YOLO(MODEL_PATH)
    MODEL_LOADED = True
    print("✅ Model başarıyla yüklendi!")
except Exception as e:
    MODEL_LOADED = False
    model = None
    print(f"❌ Model yüklenemedi: {e}")

print("=" * 60)


# ============================================================================
# ENDPOINTS
# ============================================================================

@app.get("/", response_model=dict)
async def root():
    """Ana sayfa"""
    return {
        "service": "YOLO Hotspot Detection API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "detect": "/detect (POST)"
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Servis sağlık kontrolü"""
    return HealthResponse(
        status="healthy" if MODEL_LOADED else "unhealthy",
        model_loaded=MODEL_LOADED,
        model_path=MODEL_PATH
    )


@app.post("/detect", response_model=DetectionResponse)
async def detect_hotspots(
    file: UploadFile = File(...),
    min_confidence: float = None
):
    """
    Görüntüdeki hotspotları tespit et
    
    - **file**: PNG/JPG görüntü dosyası
    - **min_confidence**: Minimum güven eşiği (varsayılan: 0.5)
    
    Returns:  Tespit edilen hotspotların listesi (% koordinatlarla)
    """
    
    start_time = time. time()
    conf_threshold = min_confidence if min_confidence else MIN_CONFIDENCE
    
    # Model kontrolü
    if not MODEL_LOADED or model is None:
        return DetectionResponse(
            success=False,
            message="Model yüklenmemiş",
            filename=file.filename or "unknown",
            image_width=0,
            image_height=0,
            detection_count=0,
            processing_time_ms=0,
            detections=[],
            error="YOLO model yüklenemedi"
        )
    
    try:
        # Görüntüyü oku
        contents = await file.read()
        nparr = np. frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(
                status_code=400, 
                detail="Görüntü dosyası okunamadı.  Geçerli bir PNG/JPG dosyası gönderin."
            )
        
        img_height, img_width = image.shape[:2]
        
        # YOLO inference
        results = model. predict(
            source=image,
            conf=conf_threshold,
            verbose=False
        )
        
        detections = []
        
        for result in results:
            boxes = result.boxes
            
            if boxes is None:
                continue
                
            for box in boxes: 
                # Koordinatları al (piksel cinsinden)
                x1, y1, x2, y2 = box. xyxy[0]. tolist()
                conf = float(box.conf[0])
                
                # Piksellerden yüzdeye çevir
                left_percent = (x1 / img_width) * 100
                top_percent = (y1 / img_height) * 100
                width_percent = ((x2 - x1) / img_width) * 100
                height_percent = ((y2 - y1) / img_height) * 100
                
                detections.append(HotspotDetection(
                    left=round(left_percent, 2),
                    top=round(top_percent, 2),
                    width=round(width_percent, 2),
                    height=round(height_percent, 2),
                    confidence=round(conf, 4),
                    label=None  # YOLO numara okuyamaz, OCR gerekir
                ))
        
        # Sonuçları pozisyona göre sırala (yukarıdan aşağıya, soldan sağa)
        detections.sort(key=lambda d: (d.top, d.left))
        
        processing_time = (time.time() - start_time) * 1000
        
        print(f"✅ {file.filename}:  {len(detections)} hotspot tespit edildi ({processing_time:.0f}ms)")
        
        return DetectionResponse(
            success=True,
            message=f"{len(detections)} hotspot tespit edildi",
            filename=file.filename or "unknown",
            image_width=img_width,
            image_height=img_height,
            detection_count=len(detections),
            processing_time_ms=round(processing_time, 2),
            detections=detections
        )
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = (time.time() - start_time) * 1000
        print(f"❌ Hata: {e}")
        
        return DetectionResponse(
            success=False,
            message="Tespit sırasında hata oluştu",
            filename=file. filename or "unknown",
            image_width=0,
            image_height=0,
            detection_count=0,
            processing_time_ms=round(processing_time, 2),
            detections=[],
            error=str(e)
        )


# ============================================================================
# ÇALIŞTIRMA
# ============================================================================

if __name__ == "__main__": 
    import uvicorn
    
    port = int(os. getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    
    print(f"\n🌐 API başlatılıyor:  http://{host}:{port}")
    print(f"📖 Swagger UI:  http://{host}:{port}/docs")
    print(f"📖 ReDoc: http://{host}:{port}/redoc\n")
    
    uvicorn. run(app, host=host, port=port)