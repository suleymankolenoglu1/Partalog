

"""
Hotspot Detector - YOLO ile balloon/hotspot tespiti
Teknik resimlerdeki parça numarası işaretlerini tespit eder. 
"""

from ultralytics import YOLO
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
import cv2
from loguru import logger


@dataclass
class Detection:
    """Tek bir tespit sonucu."""
    x1: float          # Sol üst köşe X
    y1: float          # Sol üst köşe Y
    x2: float          # Sağ alt köşe X
    y2: float          # Sağ alt köşe Y
    confidence:  float  # Güven skoru (0-1)
    class_id:  int      # Sınıf ID
    class_name: str    # Sınıf adı
    
    @property
    def bbox(self) -> Tuple[float, float, float, float]: 
        """Bounding box (x1, y1, x2, y2)."""
        return (self.x1, self.y1, self.x2, self.y2)
    
    @property
    def center(self) -> Tuple[float, float]:
        """Merkez noktası (x, y)."""
        return ((self.x1 + self.x2) / 2, (self.y1 + self.y2) / 2)
    
    @property
    def width(self) -> float:
        """Genişlik."""
        return self. x2 - self.x1
    
    @property
    def height(self) -> float:
        """Yükseklik."""
        return self.y2 - self. y1
    
    def to_dict(self) -> dict:
        """Dictionary'e çevir."""
        return {
            "x1": round(self.x1, 2),
            "y1":  round(self.y1, 2),
            "x2": round(self. x2, 2),
            "y2": round(self.y2, 2),
            "width": round(self. width, 2),
            "height":  round(self.height, 2),
            "center_x": round(self.center[0], 2),
            "center_y": round(self. center[1], 2),
            "confidence": round(self.confidence, 4),
            "class_id": self. class_id,
            "class_name": self.class_name
        }
    
    def to_normalized(self, img_width: int, img_height: int) -> dict:
        """Yüzde olarak normalize edilmiş koordinatlar (frontend için)."""
        return {
            "left": round((self.x1 / img_width) * 100, 2),
            "top":  round((self.y1 / img_height) * 100, 2),
            "width": round((self. width / img_width) * 100, 2),
            "height": round((self.height / img_height) * 100, 2),
            "confidence": round(self. confidence, 4),
            "class_name": self.class_name
        }


class HotspotDetector:
    """
    YOLO tabanlı hotspot/balloon tespit sınıfı.
    Teknik resimlerdeki parça numarası işaretlerini tespit eder.
    """
    
    def __init__(
        self,
        model_path: str,
        confidence:  float = 0.25,
        img_size: int = 1280
    ):
        """
        Args:
            model_path: YOLO model dosyası yolu (best.pt)
            confidence: Minimum güven eşiği (0-1)
            img_size: Tahmin için görüntü boyutu
        """
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.img_size = img_size
        
        # Model dosyası var mı kontrol et
        if not self.model_path. exists():
            raise FileNotFoundError(
                f"YOLO model dosyası bulunamadı:  {self.model_path}"
            )
        
        # Modeli yükle
        logger.info(f"YOLO modeli yükleniyor: {self. model_path}")
        self.model = YOLO(str(self.model_path))
        
        # Sınıf isimlerini al
        self.class_names = self.model. names
        logger.info(f"Model sınıfları: {self. class_names}")
    
    def detect(
        self,
        image: np.ndarray,
        confidence: Optional[float] = None
    ) -> List[Detection]:
        """
        Görüntüde hotspot tespiti yap.
        
        Args:
            image: OpenCV formatında görüntü (BGR)
            confidence: Opsiyonel güven eşiği (varsayılan:  init'teki değer)
        
        Returns: 
            Detection listesi
        """
        conf = confidence or self.confidence
        
        # YOLO tahmini
        results = self.model. predict(
            source=image,
            conf=conf,
            imgsz=self. img_size,
            verbose=False
        )
        
        detections = []
        
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            
            for box in boxes: 
                # Koordinatlar
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                
                # Güven skoru
                conf_score = float(box.conf[0])
                
                # Sınıf
                class_id = int(box.cls[0])
                class_name = self.class_names. get(class_id, "unknown")
                
                detection = Detection(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    confidence=conf_score,
                    class_id=class_id,
                    class_name=class_name
                )
                
                detections.append(detection)
        
        # Güven skoruna göre sırala (yüksekten düşüğe)
        detections.sort(key=lambda d: d. confidence, reverse=True)
        
        logger.debug(f"Tespit edilen hotspot sayısı:  {len(detections)}")
        
        return detections
    
    def detect_from_bytes(
        self,
        image_bytes: bytes,
        confidence: Optional[float] = None
    ) -> Tuple[List[Detection], np.ndarray]: 
        """
        Byte array'den görüntü okuyup tespit yap.
        
        Args:
            image_bytes:  Görüntü byte'ları
            confidence: Opsiyonel güven eşiği
        
        Returns: 
            (Detection listesi, OpenCV görüntüsü)
        """
        # Byte'lardan görüntü oluştur
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("Görüntü okunamadı")
        
        detections = self.detect(image, confidence)
        
        return detections, image
    
    def crop_detections(
        self,
        image: np.ndarray,
        detections: List[Detection],
        padding: int = 5
    ) -> List[Tuple[Detection, np.ndarray]]: 
        """
        Her tespit için görüntüyü kırp.
        
        Args:
            image: Orijinal görüntü
            detections: Tespit listesi
            padding:  Kırpma için ek kenar boşluğu
        
        Returns: 
            (Detection, kırpılmış görüntü) tuple listesi
        """
        img_h, img_w = image.shape[:2]
        crops = []
        
        for det in detections: 
            # Padding ekle ve sınırları kontrol et
            x1 = max(0, int(det.x1) - padding)
            y1 = max(0, int(det.y1) - padding)
            x2 = min(img_w, int(det.x2) + padding)
            y2 = min(img_h, int(det.y2) + padding)
            
            # Kırp
            crop = image[y1:y2, x1:x2]. copy()
            
            if crop.size > 0:
                crops.append((det, crop))
        
        return crops
    
    def get_info(self) -> dict:
        """Model bilgilerini döndür."""
        return {
            "model_path": str(self.model_path),
            "confidence_threshold": self.confidence,
            "img_size": self. img_size,
            "class_names": self.class_names,
            "num_classes": len(self. class_names)
        }