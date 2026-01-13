"""
OCR Reader - Hotspot içindeki numaraları okur
EasyOCR kullanarak balloon içindeki rakamları tespit eder. 
"""

import easyocr
import numpy as np
import cv2
from typing import Optional, List, Tuple
from loguru import logger


class OCRReader: 
    """
    EasyOCR tabanlı numara okuyucu. 
    Hotspot/balloon içindeki rakamları okur.
    """
    
    def __init__(
        self,
        langs: List[str] = None,
        use_gpu: bool = False
    ):
        """
        Args:
            langs:  Dil listesi (varsayılan: ['en'])
            use_gpu: GPU kullanılsın mı? 
        """
        self.langs = langs or ['en']
        self. use_gpu = use_gpu
        
        logger.info(f"OCR Reader başlatılıyor (langs={self.langs}, gpu={self.use_gpu})")
        
        # EasyOCR reader oluştur
        self.reader = easyocr.Reader(
            self.langs,
            gpu=self.use_gpu,
            verbose=False
        )
        
        logger.info("OCR Reader hazır")
    
    def read_number(
        self,
        image: np.ndarray,
        preprocess: bool = True
    ) -> Optional[str]:
        """
        Görüntüden numara oku.
        
        Args:
            image: OpenCV formatında görüntü (BGR)
            preprocess: Ön işleme uygulansın mı?
        
        Returns: 
            Okunan numara (string) veya None
        """
        if image is None or image.size == 0:
            return None
        
        try:
            # Ön işleme
            if preprocess: 
                processed = self._preprocess_image(image)
            else:
                processed = image
            
            # OCR uygula
            results = self.reader. readtext(
                processed,
                allowlist='0123456789',  # Sadece rakamlar
                detail=0,                 # Sadece metni döndür
                paragraph=False
            )
            
            if results: 
                # İlk sonucu al ve temizle
                text = results[0]. strip()
                
                # Filtre:  1-4 karakter arası olmalı (parça numaraları genelde 1-999)
                if 0 < len(text) <= 4:
                    return text
                else: 
                    logger.debug(f"OCR filtresi:  '{text}' atıldı (uzunluk: {len(text)})")
            
            return None
            
        except Exception as e:
            logger.warning(f"OCR hatası: {e}")
            return None
    
    def _preprocess_image(self, image: np. ndarray) -> np.ndarray:
        """
        OCR için görüntü ön işleme. 
        Siyah daire içindeki beyaz metni okumak için optimize edilmiş.
        """
        # 1. Gri tonlamaya çevir
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        # 2. Renkleri tersine çevir (siyah zemin + beyaz yazı → beyaz zemin + siyah yazı)
        inverted = cv2.bitwise_not(gray)
        
        # 3. Kontrast artır
        # CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(inverted)
        
        # 4. Gürültü azalt
        denoised = cv2.medianBlur(enhanced, 3)
        
        # 5. Binary threshold
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 6. Büyüt (OCR daha iyi çalışır)
        scale_factor = 3
        enlarged = cv2.resize(
            binary, 
            None, 
            fx=scale_factor, 
            fy=scale_factor, 
            interpolation=cv2.INTER_CUBIC
        )
        
        return enlarged
    
    def read_numbers_batch(
        self,
        images: List[np.ndarray]
    ) -> List[Optional[str]]:
        """
        Birden fazla görüntüden numara oku.
        
        Args:
            images: Görüntü listesi
        
        Returns: 
            Okunan numaralar listesi
        """
        results = []
        for img in images:
            result = self.read_number(img)
            results.append(result)
        return results
    
    def get_info(self) -> dict:
        """OCR bilgilerini döndür."""
        return {
            "engine": "EasyOCR",
            "languages": self.langs,
            "gpu_enabled": self.use_gpu
        }