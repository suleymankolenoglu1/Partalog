"""
Catalog Processor Service - SAM-HQ + Leader Line
"""

import numpy as np
import cv2
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from loguru import logger
import uuid
import time


@dataclass
class ProcessedPart:
    id: str
    part_number: Optional[str]
    balloon_bbox: Dict[str, float]
    balloon_center: Dict[str, float]
    balloon_confidence: float
    part_bbox: Optional[Dict[str, int]] = None
    part_centroid: Optional[Dict[str, int]] = None
    part_area: Optional[int] = None
    leader_line_end:  Optional[Dict[str, int]] = None
    embedding: Optional[List[float]] = None
    normalized:  Dict = field(default_factory=dict)


@dataclass
class ProcessingResult:
    success: bool
    message: str
    image_width: int
    image_height: int
    processing_time_ms: float
    parts:  List[ProcessedPart]
    segments_found: int = 0


class CatalogProcessor:
    def __init__(self, detector, ocr_reader, segmenter, embedder, vector_store):
        self.detector = detector
        self.ocr = ocr_reader
        self.segmenter = segmenter
        self.embedder = embedder
        self.vector_store = vector_store
        logger.info("CatalogProcessor hazır")
    
    def process_image(
        self,
        image:  np.ndarray,
        extract_embeddings: bool = True,
        save_to_db: bool = False,
        catalog_id: Optional[str] = None
    ) -> ProcessingResult:
        start_time = time. time()
        img_h, img_w = image.shape[:2]
        
        logger.info(f"Görüntü işleniyor: {img_w}x{img_h}")
        
        # Balloon Tespiti
        logger.debug("Adım 1: Balloon tespiti...")
        
        if self.detector is None:
            return ProcessingResult(
                success=False, message="YOLO yüklenmemiş",
                image_width=img_w, image_height=img_h,
                processing_time_ms=0, parts=[]
            )
        
        detections = self.detector.detect(image)
        logger.debug(f"  → {len(detections)} balloon bulundu")
        
        if not detections:
            return ProcessingResult(
                success=True, message="Balloon bulunamadı",
                image_width=img_w, image_height=img_h,
                processing_time_ms=(time.time() - start_time) * 1000,
                parts=[]
            )
        
        # SAM hazırla
        if self.segmenter and self.segmenter. use_sam:
            logger.debug("Adım 2: SAM-HQ görüntü hazırlanıyor...")
            self.segmenter. set_image(image)
        
        # Her balloon için işlem
        logger.debug("Adım 3: Balloon işleme...")
        
        processed_parts = []
        segments_found = 0
        
        for i, det in enumerate(detections):
            part_id = str(uuid.uuid4())[: 8]
            
            # OCR
            part_number = None
            if self.ocr:
                try:
                    crops = self.detector.crop_detections(image, [det], padding=5)
                    if crops:
                        _, crop_img = crops[0]
                        part_number = self.ocr.read_number(crop_img)
                except: 
                    pass
            
            # SAM-HQ Segmentasyon
            segment = None
            part_crop = None
            leader_line_end = None
            
            if self.segmenter: 
                try: 
                    balloon_center = det. center
                    balloon_bbox = (det.x1, det.y1, det.x2, det.y2)
                    
                    segment = self.segmenter.segment_from_balloon(
                        image, balloon_center, balloon_bbox
                    )
                    
                    if segment:
                        segments_found += 1
                        part_crop = segment.cropped_image
                        leader_line_end = segment.leader_line_end
                        
                        if part_crop is None:
                            part_crop = self.segmenter. crop_segment(image, segment)
                        
                        logger.debug(f"  #{part_number or i}:  Segment ✓ (score: {segment.score:.2f})")
                    else:
                        logger.debug(f"  #{part_number or i}:  Segment ✗")
                except Exception as e: 
                    logger.warning(f"Segmentasyon hatası:  {e}")
            
            # Fallback
            if part_crop is None:
                part_crop = self._estimate_part_region(image, det)
            
            # Embedding
            embedding = None
            if extract_embeddings and self.embedder and part_crop is not None and part_crop.size > 0:
                try:
                    embedding = self.embedder.embed_image(part_crop)
                except: 
                    pass
            
            # ProcessedPart - ✅ int() ile çevir
            balloon_center = det.center
            processed_part = ProcessedPart(
                id=part_id,
                part_number=part_number,
                balloon_bbox={
                    "x1": float(det.x1), 
                    "y1": float(det.y1), 
                    "x2": float(det.x2), 
                    "y2": float(det.y2)
                },
                balloon_center={
                    "x": float(balloon_center[0]), 
                    "y": float(balloon_center[1])
                },
                balloon_confidence=float(det.confidence),
                embedding=embedding. tolist() if embedding is not None else None,
                normalized={
                    "left": round((det.x1 / img_w) * 100, 2),
                    "top": round((det.y1 / img_h) * 100, 2),
                    "width": round((det. width / img_w) * 100, 2),
                    "height": round((det.height / img_h) * 100, 2)
                }
            )
            
            # Segment bilgisi - ✅ int() ile çevir
            if segment: 
                processed_part.part_bbox = {
                    "x":  int(segment.bbox[0]), 
                    "y": int(segment.bbox[1]),
                    "width": int(segment. bbox[2]), 
                    "height": int(segment.bbox[3])
                }
                processed_part.part_centroid = {
                    "x":  int(segment.centroid[0]), 
                    "y": int(segment. centroid[1])
                }
                processed_part.part_area = int(segment.area)
                if leader_line_end: 
                    processed_part.leader_line_end = {
                        "x":  int(leader_line_end[0]), 
                        "y": int(leader_line_end[1])
                    }
            
            # DB kaydet
            if save_to_db and embedding is not None and self.vector_store:
                try: 
                    db_id = f"{catalog_id}_{part_number or part_id}" if catalog_id else part_id
                    self.vector_store.add(
                        id=db_id, embedding=embedding,
                        metadata={"part_number":  part_number, "catalog_id": catalog_id}
                    )
                except: 
                    pass
            
            processed_parts.append(processed_part)
        
        # Sırala
        processed_parts.sort(
            key=lambda p: (int(p.part_number) if p.part_number and p.part_number. isdigit() else 999)
        )
        
        processing_time = (time.time() - start_time) * 1000
        
        logger.info(f"Tamamlandı:  {len(processed_parts)} parça, {segments_found} segment, {processing_time:.2f}ms")
        
        return ProcessingResult(
            success=True,
            message=f"{len(processed_parts)} parça ({segments_found} segment)",
            image_width=int(img_w),
            image_height=int(img_h),
            processing_time_ms=round(processing_time, 2),
            parts=processed_parts,
            segments_found=int(segments_found)
        )
    
    def _estimate_part_region(self, image:  np.ndarray, detection, region_size: int = 100):
        img_h, img_w = image.shape[:2]
        cx = int((detection.x1 + detection.x2) / 2)
        below_y = int(detection.y2 + 20)
        x1, x2 = max(0, cx - region_size), min(img_w, cx + region_size)
        y1, y2 = max(0, below_y), min(img_h, below_y + region_size * 2)
        return image[y1:y2, x1:x2]. copy() if x2 > x1 and y2 > y1 else None
    
    def process_image_from_bytes(self, image_bytes:  bytes, **kwargs) -> ProcessingResult:
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if image is None:
            return ProcessingResult(
                success=False, message="Görüntü okunamadı",
                image_width=0, image_height=0, processing_time_ms=0, parts=[]
            )
        return self.process_image(image, **kwargs)