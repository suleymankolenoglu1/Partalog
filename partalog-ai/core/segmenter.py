"""
Part Segmenter - SAM-HQ + Leader Line Takibi
"""

import numpy as np
import cv2
from typing import List, Tuple, Optional
from dataclasses import dataclass
from loguru import logger
from pathlib import Path
import torch

# SAM-HQ import
SAM_HQ_AVAILABLE = False
SAM_AVAILABLE = False

try:
    from segment_anything_hq import sam_model_registry as sam_hq_registry
    from segment_anything_hq import SamPredictor as SamHQPredictor
    SAM_HQ_AVAILABLE = True
    logger.info("SAM-HQ kütüphanesi yüklendi")
except ImportError: 
    try:
        from segment_anything import sam_model_registry, SamPredictor
        SAM_AVAILABLE = True
        logger.info("SAM kütüphanesi yüklendi")
    except ImportError:
        logger.warning("SAM kütüphanesi bulunamadı")


@dataclass
class PartSegment:
    """Segmente edilmiş parça bilgisi."""
    id: int
    mask: np.ndarray
    bbox: Tuple[int, int, int, int]
    area: int
    centroid: Tuple[int, int]
    score: float = 0.0
    leader_line_end: Optional[Tuple[int, int]] = None
    cropped_image: Optional[np. ndarray] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "bbox": {"x": self.bbox[0], "y":  self.bbox[1], "width": self.bbox[2], "height": self. bbox[3]},
            "area":  self.area,
            "centroid":  {"x": self. centroid[0], "y": self. centroid[1]},
            "score": round(self.score, 3),
            "leader_line_end": {"x": self.leader_line_end[0], "y":  self.leader_line_end[1]} if self.leader_line_end else None
        }


class PartSegmenter: 
    """SAM-HQ ile parça segmentasyonu."""
    
    def __init__(
        self,
        model_path: Optional[str] = None,
        model_type: str = "vit_b",
        use_sam:  bool = True,
        min_area: int = 100,
        max_area_ratio: float = 0.5
    ):
        self.min_area = min_area
        self. max_area_ratio = max_area_ratio
        self. predictor = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self._current_image = None
        self. backend = "OpenCV"
        
        if use_sam and model_path: 
            model_file = Path(model_path)
            if model_file.exists():
                self._load_sam_hq(str(model_file), model_type)
        
        if self.predictor is None:
            logger.info("OpenCV tabanlı segmentasyon aktif")
    
    def _load_sam_hq(self, model_path: str, model_type: str):
        """SAM-HQ modelini yükle - CPU/GPU uyumlu."""
        logger.info(f"SAM-HQ modeli yükleniyor: {model_path}")
        
        try:
            # ✅ DÜZELTME: CPU için map_location ekle
            checkpoint = torch.load(model_path, map_location=self.device)
            
            sam = sam_hq_registry[model_type]()
            sam.load_state_dict(checkpoint)
            sam.to(self. device)
            
            self.predictor = SamHQPredictor(sam)
            self.backend = "SAM-HQ"
            logger.success(f"SAM-HQ modeli yüklendi (device: {self.device})")
            
        except Exception as e:
            logger. error(f"SAM-HQ yükleme hatası: {e}")
            # Alternatif yükleme yöntemi dene
            try: 
                self._load_sam_hq_alternative(model_path, model_type)
            except Exception as e2:
                logger.error(f"Alternatif yükleme de başarısız: {e2}")
    
    def _load_sam_hq_alternative(self, model_path: str, model_type:  str):
        """Alternatif yükleme yöntemi."""
        logger.info("Alternatif SAM-HQ yükleme deneniyor...")
        
        # Doğrudan checkpoint ile yükle
        sam = sam_hq_registry[model_type](checkpoint=model_path)
        
        # CPU'ya taşı
        if self.device == "cpu":
            sam = sam.cpu()
        else:
            sam = sam.to(self.device)
        
        self.predictor = SamHQPredictor(sam)
        self.backend = "SAM-HQ"
        logger.success(f"SAM-HQ modeli yüklendi (alternatif, device: {self. device})")
    
    @property
    def use_sam(self) -> bool:
        return self.predictor is not None
    
    def set_image(self, image: np.ndarray):
        """SAM için görüntüyü ayarla."""
        if self.predictor:
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            self.predictor.set_image(image_rgb)
            self._current_image = image
            logger.debug(f"{self.backend} görüntü ayarlandı")
    
    def find_leader_line_endpoint(
        self,
        image: np.ndarray,
        balloon_center: Tuple[int, int],
        balloon_bbox: Tuple[float, float, float, float],
        search_radius: int = 300
    ) -> Optional[Tuple[int, int]]: 
        """Balloon'dan çıkan çizgiyi takip et."""
        img_h, img_w = image.shape[:2]
        bx, by = int(balloon_center[0]), int(balloon_center[1])
        x1, y1, x2, y2 = map(int, balloon_bbox)
        
        search_x1 = max(0, bx - search_radius)
        search_y1 = max(0, by - search_radius)
        search_x2 = min(img_w, bx + search_radius)
        search_y2 = min(img_h, by + search_radius)
        
        roi = image[search_y1:search_y2, search_x1:search_x2]. copy()
        if roi.size == 0:
            return None
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, 25, minLineLength=15, maxLineGap=10)
        
        if lines is None:
            return None
        
        balloon_local_x = bx - search_x1
        balloon_local_y = by - search_y1
        balloon_radius = max(x2 - x1, y2 - y1) / 2 + 15
        
        best_endpoint = None
        max_distance = 0
        
        for line in lines:
            lx1, ly1, lx2, ly2 = line[0]
            
            dist_to_start = np.sqrt((lx1 - balloon_local_x)**2 + (ly1 - balloon_local_y)**2)
            dist_to_end = np.sqrt((lx2 - balloon_local_x)**2 + (ly2 - balloon_local_y)**2)
            
            if dist_to_start < balloon_radius and dist_to_end > max_distance: 
                max_distance = dist_to_end
                best_endpoint = (lx2 + search_x1, ly2 + search_y1)
            elif dist_to_end < balloon_radius and dist_to_start > max_distance: 
                max_distance = dist_to_start
                best_endpoint = (lx1 + search_x1, ly1 + search_y1)
        
        return best_endpoint
    
    def segment_at_point(
        self,
        image: np.ndarray,
        point: Tuple[int, int]
    ) -> Optional[PartSegment]:
        """Noktadaki parçayı segmente et."""
        if self.predictor:
            return self._segment_at_point_sam(image, point)
        else:
            return self._segment_at_point_opencv(image, point)
    
    def _segment_at_point_sam(
        self,
        image: np.ndarray,
        point: Tuple[int, int]
    ) -> Optional[PartSegment]: 
        """SAM-HQ ile segmentasyon."""
        try:
            if self._current_image is None or self._current_image.shape != image. shape:
                self.set_image(image)
            
            input_point = np.array([[point[0], point[1]]])
            input_label = np.array([1])
            
            masks, scores, _ = self.predictor.predict(
                point_coords=input_point,
                point_labels=input_label,
                multimask_output=True
            )
            
            best_idx = np.argmax(scores)
            mask = masks[best_idx]. astype(np. uint8)
            score = float(scores[best_idx])
            
            if mask.sum() == 0:
                return None
            
            coords = np.where(mask > 0)
            if len(coords[0]) == 0:
                return None
            
            y_min, y_max = coords[0].min(), coords[0].max()
            x_min, x_max = coords[1].min(), coords[1].max()
            
            area = int(mask.sum())
            if area < self.min_area: 
                return None
            
            img_area = image.shape[0] * image. shape[1]
            if area > img_area * self. max_area_ratio:
                return None
            
            M = cv2.moments(mask)
            cx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else point[0]
            cy = int(M["m01"] / M["m00"]) if M["m00"] > 0 else point[1]
            
            cropped = image[max(0,y_min-5):min(image.shape[0],y_max+5), 
                           max(0,x_min-5):min(image.shape[1],x_max+5)].copy()
            
            return PartSegment(
                id=0,
                mask=mask,
                bbox=(x_min, y_min, x_max - x_min, y_max - y_min),
                area=area,
                centroid=(cx, cy),
                score=score,
                cropped_image=cropped
            )
        except Exception as e: 
            logger.error(f"SAM-HQ segmentasyon hatası: {e}")
            return None
    
    def _segment_at_point_opencv(
        self,
        image: np. ndarray,
        point: Tuple[int, int]
    ) -> Optional[PartSegment]: 
        """OpenCV fallback."""
        try: 
            img_h, img_w = image.shape[:2]
            px, py = point
            
            if px < 0 or px >= img_w or py < 0 or py >= img_h: 
                return None
            
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
            
            flood_mask = np.zeros((img_h + 2, img_w + 2), np.uint8)
            flood = binary. copy()
            cv2.floodFill(flood, flood_mask, point, 128)
            
            result_mask = (flood == 128).astype(np.uint8)
            area = int(result_mask.sum())
            
            if area < self.min_area:
                return None
            
            coords = np.where(result_mask > 0)
            if len(coords[0]) == 0:
                return None
            
            y_min, y_max = coords[0]. min(), coords[0].max()
            x_min, x_max = coords[1].min(), coords[1].max()
            
            M = cv2.moments(result_mask)
            cx = int(M["m10"] / M["m00"]) if M["m00"] > 0 else px
            cy = int(M["m01"] / M["m00"]) if M["m00"] > 0 else py
            
            cropped = image[y_min:y_max, x_min:x_max]. copy()
            
            return PartSegment(
                id=0,
                mask=result_mask,
                bbox=(x_min, y_min, x_max - x_min, y_max - y_min),
                area=area,
                centroid=(cx, cy),
                score=0.5,
                cropped_image=cropped
            )
        except Exception as e:
            logger.error(f"OpenCV segmentasyon hatası:  {e}")
            return None
    
    def segment_from_balloon(
        self,
        image: np.ndarray,
        balloon_center:  Tuple[int, int],
        balloon_bbox: Tuple[float, float, float, float]
    ) -> Optional[PartSegment]:
        """Balloon'dan çıkan çizgiyi takip ederek parçayı bul."""
        endpoint = self.find_leader_line_endpoint(image, balloon_center, balloon_bbox)
        
        if endpoint is None: 
            x1, y1, x2, y2 = balloon_bbox
            img_h = image.shape[0]
            fallback_y = min(int(y2 + 30), img_h - 5)
            endpoint = (int((x1 + x2) / 2), fallback_y)
        
        segment = self. segment_at_point(image, endpoint)
        
        if segment: 
            segment.leader_line_end = endpoint
        
        return segment
    
    def crop_segment(self, image: np.ndarray, segment: PartSegment, padding: int = 10) -> np.ndarray:
        """Segmenti kırp."""
        if segment.cropped_image is not None:
            return segment.cropped_image
        
        x, y, w, h = segment.bbox
        img_h, img_w = image.shape[:2]
        
        return image[max(0,y-padding):min(img_h,y+h+padding), 
                    max(0,x-padding):min(img_w,x+w+padding)].copy()
    
    def get_info(self) -> dict:
        return {
            "backend": self.backend,
            "device": self.device,
            "min_area": self. min_area,
            "leader_line_tracking": True
        }