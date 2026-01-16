"""
Hotspot OCR - Balloon içindeki numaraları okur
EasyOCR + OpenCV ön işleme + Akıllı Filtreleme v2
"""

import easyocr
import numpy as np
import cv2
from typing import Optional, List, Tuple
from loguru import logger
import re
from collections import Counter


class HotspotOCR:
    """
    Hotspot/balloon içindeki rakamları okur. 
    Siyah daire içindeki beyaz numaralar için optimize edilmiş. 
    """
    
    def __init__(self, use_gpu: bool = False):
        self.use_gpu = use_gpu
        
        logger.info("OCR Reader başlatılıyor (gpu={})".format(self.use_gpu))
        
        self.reader = easyocr.Reader(
            ['en'],
            gpu=self.use_gpu,
            verbose=False
        )
        
        logger.info("OCR Reader hazır")
    
    def read_number(self, image: np.ndarray) -> Optional[str]:
        """
        Hotspot görüntüsünden numara oku. 
        Merkez bölgeye odaklanarak kenar gürültüsünü azaltır.
        """
        if image is None or image.size == 0:
            return None
        
        # Birden fazla yöntemle oku
        candidates = []
        
        methods = [
            ("center_inverted", lambda img: self._preprocess_inverted(self._crop_center(img, 0.6))),
            ("center_adaptive", lambda img: self._preprocess_adaptive(self._crop_center(img, 0.6))),
            ("full_inverted", self._preprocess_inverted),
            ("mask_circle", self._preprocess_with_circle_mask),
        ]
        
        for method_name, method in methods:
            try:
                processed = method(image)
                result, confidence = self._ocr_read_with_confidence(processed)
                if result: 
                    candidates. append((result, confidence, method_name))
            except Exception as e:
                logger. debug("OCR method '{}' failed: {}".format(method_name, str(e)))
                continue
        
        if not candidates: 
            return None
        
        # En iyi sonucu seç
        best_result = self._select_best_result(candidates)
        
        if best_result:
            logger.debug("OCR final:  '{}' (candidates: {})".format(
                best_result,
                [(c[0], round(c[1], 2)) for c in candidates]
            ))
        
        return best_result
    
    def _crop_center(self, image: np.ndarray, ratio: float = 0.7) -> np.ndarray:
        """Görüntünün merkez bölgesini kırp."""
        h, w = image. shape[:2]
        
        margin_x = int(w * (1 - ratio) / 2)
        margin_y = int(h * (1 - ratio) / 2)
        
        margin_x = max(margin_x, 3)
        margin_y = max(margin_y, 3)
        
        cropped = image[margin_y:h-margin_y, margin_x:w-margin_x]
        
        if cropped.shape[0] < 10 or cropped. shape[1] < 10:
            return image
        
        return cropped
    
    def _preprocess_with_circle_mask(self, image: np.ndarray) -> np.ndarray:
        """Daire maskesi uygula - sadece balloon içini al."""
        h, w = image. shape[:2]
        
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else: 
            gray = image. copy()
        
        # Daire maskesi oluştur (daha küçük - %80)
        mask = np.zeros((h, w), dtype=np.uint8)
        center = (w // 2, h // 2)
        radius = int(min(w, h) * 0.4)  # %40 radius = %80 çap
        cv2.circle(mask, center, radius, 255, -1)
        
        masked = cv2.bitwise_and(gray, gray, mask=mask)
        masked[mask == 0] = 255
        
        inverted = cv2.bitwise_not(masked)
        _, binary = cv2.threshold(inverted, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        enlarged = cv2.resize(binary, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        
        return enlarged
    
    def _ocr_read_with_confidence(self, image: np.ndarray) -> Tuple[Optional[str], float]: 
        """OCR uygula ve confidence ile birlikte döndür."""
        results = self.reader. readtext(
            image,
            allowlist='0123456789',
            detail=1,
            paragraph=False
        )
        
        if not results: 
            return None, 0.0
        
        # En yüksek confidence'a sahip sonucu al
        best_result = max(results, key=lambda x: x[2])
        text = best_result[1]. strip()
        confidence = best_result[2]
        
        # Sadece rakamları al
        text = re.sub(r'[^0-9]', '', text)
        
        if not text:
            return None, 0.0
        
        # === DÜZELTME KURALLARI ===
        
        # 1-2 haneli:  direkt kabul
        if len(text) <= 2:
            return text, confidence
        
        # 3 haneli: baştaki karakter muhtemelen gürültü
        if len(text) == 3:
            corrected = self._correct_3digit(text, confidence)
            return corrected
        
        # 4+ haneli: çok fazla gürültü, düzeltmeye çalış
        if len(text) >= 4:
            corrected = self._correct_4digit_plus(text, confidence)
            return corrected
        
        return None, 0.0
    
    def _correct_3digit(self, text: str, confidence: float) -> Tuple[Optional[str], float]: 
        """
        3 haneli sonuçları düzelt.
        Örn: 413 -> 13, 512 -> 12, 822 -> 22
        """
        # Baştaki karakter genellikle yanlış (çerçeve/çizgi olarak algılanıyor)
        first_char = text[0]
        rest = text[1:]
        
        # Sık yanlış okunan baş karakterler:  4, 5, 8, 1, 2, 3
        # Bunlar genellikle balloon kenarı veya leader line
        suspicious_first_chars = ['4', '5', '8', '1', '2', '3', '7']
        
        if first_char in suspicious_first_chars: 
            # Geri kalan 2 hane geçerli bir numara mı?
            if rest. isdigit() and len(rest) == 2:
                # Confidence'ı düşür çünkü düzeltme yaptık
                return rest, confidence * 0.85
        
        # Sondaki karakter tekrar mı?  (313 -> 31)
        if text[-1] == text[-2]: 
            return text[:-1], confidence * 0.9
        
        # Eğer confidence düşükse, kabul etme
        if confidence < 0.6:
            return None, 0.0
        
        # Aksi halde olduğu gibi döndür
        return text, confidence
    
    def _correct_4digit_plus(self, text:  str, confidence: float) -> Tuple[Optional[str], float]:
        """
        4+ haneli sonuçları düzelt.
        Çok fazla gürültü var, agresif düzeltme. 
        """
        # Baştaki 1-2 karakteri at
        if len(text) == 4:
            # İlk karakteri at
            candidate = text[1:]
            if candidate.isdigit():
                return candidate, confidence * 0.7
            
            # İlk 2 karakteri at
            candidate = text[2:]
            if candidate.isdigit() and len(candidate) >= 1:
                return candidate, confidence * 0.6
        
        # 5+ karakter:  ortadaki 2 karakteri al
        if len(text) >= 5:
            mid = len(text) // 2
            candidate = text[mid-1:mid+1]
            if candidate.isdigit():
                return candidate, confidence * 0.5
        
        return None, 0.0
    
    def _select_best_result(self, candidates: List[Tuple[str, float, str]]) -> Optional[str]:
        """
        Birden fazla OCR sonucundan en iyisini seç. 
        """
        if not candidates:
            return None
        
        if len(candidates) == 1:
            result, conf, _ = candidates[0]
            # Tek sonuç ve düşük confidence ise reddet
            if conf < 0.3:
                return None
            return result
        
        # Sonuçları grupla
        result_groups = {}
        for result, conf, method in candidates: 
            if result not in result_groups: 
                result_groups[result] = []
            result_groups[result].append((conf, method))
        
        # En çok tekrar eden ve yüksek confidence'lı sonucu bul
        best_result = None
        best_score = 0
        
        for result, occurrences in result_groups.items():
            count = len(occurrences)
            avg_conf = sum(c for c, _ in occurrences) / count
            
            # Skor = tekrar sayısı * ortalama confidence * uzunluk cezası
            length_penalty = 1.0 if len(result) <= 2 else 0.8 if len(result) == 3 else 0.5
            score = count * avg_conf * length_penalty
            
            if score > best_score: 
                best_score = score
                best_result = result
        
        # Minimum skor kontrolü
        if best_score < 0.5:
            # Düşük skorlu sonuçlar arasından en kısa ve en yüksek conf olanı seç
            candidates. sort(key=lambda x: (len(x[0]), -x[1]))
            result, conf, _ = candidates[0]
            if conf >= 0.4 and len(result) <= 2:
                return result
            return None
        
        return best_result
    
    def _preprocess_inverted(self, image: np.ndarray) -> np.ndarray:
        """Siyah zemin beyaz yazı için ters çevir."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        inverted = cv2.bitwise_not(gray)
        
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(inverted)
        
        denoised = cv2.medianBlur(enhanced, 3)
        
        _, binary = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        enlarged = cv2.resize(binary, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        
        return enlarged
    
    def _preprocess_adaptive(self, image: np.ndarray) -> np.ndarray:
        """Adaptive threshold ile ön işleme."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2
        )
        
        kernel = np.ones((2, 2), np.uint8)
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        enlarged = cv2.resize(binary, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
        
        return enlarged
    
    def read_numbers_batch(self, images: List[np. ndarray]) -> List[Optional[str]]: 
        """Birden fazla görüntüden numara oku."""
        return [self.read_number(img) for img in images]
    
    def get_info(self) -> dict:
        """OCR bilgilerini döndür."""
        return {
            "engine": "EasyOCR",
            "gpu_enabled": self.use_gpu,
            "allowed_chars": "0123456789",
            "features": ["center_crop", "circle_mask", "voting", "3digit_correction", "4digit_correction"]
        }


# Geriye uyumluluk
OCRReader = HotspotOCR