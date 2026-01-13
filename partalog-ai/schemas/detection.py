"""
Detection Schemas - Tespit API modelleri
"""

from pydantic import BaseModel, Field
from typing import List, Optional


class DetectionResult(BaseModel):
    """Tek bir tespit sonucu."""
    x1: float = Field(... , description="Sol üst köşe X koordinatı (piksel)")
    y1: float = Field(..., description="Sol üst köşe Y koordinatı (piksel)")
    x2: float = Field(... , description="Sağ alt köşe X koordinatı (piksel)")
    y2: float = Field(..., description="Sağ alt köşe Y koordinatı (piksel)")
    width: float = Field(... , description="Genişlik (piksel)")
    height: float = Field(..., description="Yükseklik (piksel)")
    center_x: float = Field(..., description="Merkez X koordinatı (piksel)")
    center_y: float = Field(... , description="Merkez Y koordinatı (piksel)")
    confidence: float = Field(..., ge=0, le=1, description="Güven skoru (0-1)")
    class_id:  int = Field(..., description="Sınıf ID")
    class_name:  str = Field(..., description="Sınıf adı")
    label: Optional[str] = Field(None, description="OCR ile okunan metin")


class NormalizedDetection(BaseModel):
    """Yüzde olarak normalize edilmiş tespit (frontend için)."""
    left: float = Field(... , ge=0, le=100, description="Sol konum (%)")
    top: float = Field(... , ge=0, le=100, description="Üst konum (%)")
    width: float = Field(..., ge=0, le=100, description="Genişlik (%)")
    height: float = Field(... , ge=0, le=100, description="Yükseklik (%)")
    confidence: float = Field(... , ge=0, le=1, description="Güven skoru")
    class_name: str = Field(... , description="Sınıf adı")
    label: Optional[str] = Field(None, description="OCR ile okunan metin")


class DetectionResponse(BaseModel):
    """Tespit API yanıtı."""
    success: bool = Field(... , description="İşlem başarılı mı?")
    message: str = Field(... , description="Açıklama mesajı")
    image_width: int = Field(... , description="Görüntü genişliği (piksel)")
    image_height: int = Field(... , description="Görüntü yüksekliği (piksel)")
    detection_count: int = Field(... , description="Tespit edilen hotspot sayısı")
    processing_time_ms: float = Field(..., description="İşlem süresi (ms)")
    detections: List[DetectionResult] = Field(..., description="Tespit listesi")


class NormalizedDetectionResponse(BaseModel):
    """Normalize edilmiş tespit API yanıtı (frontend için)."""
    success: bool
    message: str
    detection_count: int
    processing_time_ms: float
    detections: List[NormalizedDetection]