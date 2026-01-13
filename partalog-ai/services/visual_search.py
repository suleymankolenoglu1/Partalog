
"""
Visual Search Service - Görsel arama servisi
Kullanıcının çektiği fotoğrafla parça arar.
"""

import numpy as np
import cv2
from typing import List, Dict, Optional
from dataclasses import dataclass
from loguru import logger
import time


@dataclass
class SearchMatch:
    """Arama sonucu eşleşme."""
    part_id: str
    part_number: Optional[str]
    similarity:  float
    catalog_id: Optional[str]
    metadata: Dict
    
    def to_dict(self) -> dict:
        return {
            "part_id": self. part_id,
            "part_number": self.part_number,
            "similarity": round(self.similarity * 100, 2),  # Yüzde olarak
            "catalog_id": self.catalog_id,
            "metadata": self.metadata
        }


@dataclass
class SearchResult:
    """Arama sonucu."""
    success: bool
    message: str
    query_processed:  bool
    processing_time_ms:  float
    match_count: int
    matches: List[SearchMatch]
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self. message,
            "processing_time_ms":  self.processing_time_ms,
            "match_count":  self.match_count,
            "matches": [m.to_dict() for m in self. matches]
        }


class VisualSearchService:
    """
    Görsel arama servisi.
    Fotoğrafla parça arar. 
    """
    
    def __init__(
        self,
        embedder,       # ImageEmbedder
        vector_store    # VectorStore
    ):
        self.embedder = embedder
        self. vector_store = vector_store
        
        logger.info("VisualSearchService hazır")
    
    def search(
        self,
        image: np.ndarray,
        top_k: int = 10,
        threshold: float = 0.5
    ) -> SearchResult:
        """
        Görsel ile arama yap.
        
        Args:
            image: Aranacak parça görseli
            top_k: Döndürülecek maksimum sonuç
            threshold: Minimum benzerlik eşiği (0-1)
        
        Returns: 
            SearchResult
        """
        start_time = time.time()
        
        # Kontroller
        if self.embedder is None: 
            return SearchResult(
                success=False,
                message="CLIP embedder yüklenmemiş",
                query_processed=False,
                processing_time_ms=0,
                match_count=0,
                matches=[]
            )
        
        if self.vector_store is None:
            return SearchResult(
                success=False,
                message="Vector store yüklenmemiş",
                query_processed=False,
                processing_time_ms=0,
                match_count=0,
                matches=[]
            )
        
        # Veritabanında kayıt var mı?
        db_count = self.vector_store.count()
        if db_count == 0:
            return SearchResult(
                success=True,
                message="Veritabanında henüz parça yok",
                query_processed=True,
                processing_time_ms=(time.time() - start_time) * 1000,
                match_count=0,
                matches=[]
            )
        
        # Embedding çıkar
        logger.debug("Sorgu embedding çıkarılıyor...")
        query_embedding = self. embedder.embed_image(image)
        
        # Arama yap
        logger. debug(f"Vector DB'de arama yapılıyor (top_k={top_k})...")
        raw_results = self.vector_store.search(
            query_embedding=query_embedding,
            top_k=top_k
        )
        
        # Filtrele ve formatla
        matches = []
        for result in raw_results: 
            similarity = result["similarity"]
            
            if similarity >= threshold:
                metadata = result. get("metadata", {})
                
                matches.append(SearchMatch(
                    part_id=result["id"],
                    part_number=metadata.get("part_number"),
                    similarity=similarity,
                    catalog_id=metadata.get("catalog_id"),
                    metadata=metadata
                ))
        
        processing_time = (time.time() - start_time) * 1000
        
        logger.info(f"Arama tamamlandı: {len(matches)} eşleşme, {processing_time:. 2f}ms")
        
        return SearchResult(
            success=True,
            message=f"{len(matches)} eşleşme bulundu",
            query_processed=True,
            processing_time_ms=round(processing_time, 2),
            match_count=len(matches),
            matches=matches
        )
    
    def search_from_bytes(
        self,
        image_bytes: bytes,
        **kwargs
    ) -> SearchResult:
        """Byte array'den görsel arama."""
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            return SearchResult(
                success=False,
                message="Görüntü okunamadı",
                query_processed=False,
                processing_time_ms=0,
                match_count=0,
                matches=[]
            )
        
        return self.search(image, **kwargs)