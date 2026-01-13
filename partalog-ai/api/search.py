"""
Search API - Arama endpoint'leri
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from loguru import logger


router = APIRouter()

# Servis referansları
_search_service = None
_processor_service = None


def set_search_service(service):
    global _search_service
    _search_service = service


def set_processor_service(service):
    global _processor_service
    _processor_service = service


# ============================================
# SCHEMAS
# ============================================

class SearchMatchResponse(BaseModel):
    part_id: str
    part_number:  Optional[str]
    similarity: float = Field(... , description="Benzerlik yüzdesi (0-100)")
    catalog_id: Optional[str]


class VisualSearchResponse(BaseModel):
    success: bool
    message: str
    processing_time_ms:  float
    match_count: int
    matches: List[SearchMatchResponse]


# ============================================
# ENDPOINTS
# ============================================

@router.post(
    "/visual",
    response_model=VisualSearchResponse,
    summary="Görsel Arama",
    description="Fotoğraf ile parça arar."
)
async def visual_search(
    file: UploadFile = File(..., description="Parça fotoğrafı"),
    top_k: int = Query(default=10, ge=1, le=50, description="Maksimum sonuç sayısı"),
    threshold: float = Query(default=0.5, ge=0.0, le=1.0, description="Minimum benzerlik (0-1)")
):
    """
    Yüklenen fotoğrafla veritabanında parça arar. 
    
    - **file**: Parça fotoğrafı (JPG, PNG)
    - **top_k**: Döndürülecek maksimum sonuç
    - **threshold**:  Minimum benzerlik eşiği
    
    Döndürülen similarity değeri yüzde cinsindendir (0-100).
    """
    if _search_service is None:
        raise HTTPException(status_code=503, detail="Arama servisi hazır değil")
    
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Boş dosya")
    except Exception as e: 
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {str(e)}")
    
    result = _search_service.search_from_bytes(
        contents,
        top_k=top_k,
        threshold=threshold
    )
    
    return VisualSearchResponse(
        success=result.success,
        message=result.message,
        processing_time_ms=result.processing_time_ms,
        match_count=result.match_count,
        matches=[
            SearchMatchResponse(
                part_id=m.part_id,
                part_number=m.part_number,
                similarity=m.similarity * 100,  # Yüzdeye çevir
                catalog_id=m.catalog_id
            )
            for m in result.matches
        ]
    )