"""
Table API - PaddleOCR Tablo Okuma Endpoint'leri
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Form
from pydantic import BaseModel, Field
from typing import List, Optional
from loguru import logger
import time
import os

router = APIRouter()


# ============================================
# SCHEMAS
# ============================================

class ProductResult(BaseModel):
    ref_number: int = Field(..., description="Referans numarası")
    part_code: str = Field(..., description="Parça kodu")
    part_name: str = Field(..., description="Parça adı")
    confidence: float = Field(default=1.0, description="Güven skoru")


class TableResult(BaseModel):
    table_index: int
    row_count: int
    product_count: int
    products: List[ProductResult]
    bbox: Optional[List[float]] = None


class TableExtractionResponse(BaseModel):
    success: bool
    message: str
    page_number: int
    table_count: int
    total_products: int
    processing_time_ms: float
    tables: List[TableResult]


class TextResult(BaseModel):
    text: str
    confidence: float
    bbox: List[List[float]]
    center_x: float
    center_y: float


class OcrResponse(BaseModel):
    success: bool
    message: str
    text_count: int
    processing_time_ms: float
    image_width: int = 0
    image_height:  int = 0
    texts: List[TextResult]


# ============================================
# MODEL ACCESS
# ============================================

def get_table_reader():
    """Table reader'ı al."""
    from main import models
    
    if "table_reader" not in models or models["table_reader"] is None: 
        raise HTTPException(
            status_code=503,
            detail="PaddleOCR Table Reader yüklenmemiş."
        )
    
    return models["table_reader"]


# ============================================
# ENDPOINTS
# ============================================

@router. post("/extract-table", response_model=TableExtractionResponse)
async def extract_table_from_file(
    file: UploadFile = File(..., description="PDF veya görüntü dosyası"),
    page_number: int = Query(default=1, ge=1, description="Sayfa numarası"),
    table_x: Optional[float] = Query(default=None, ge=0, le=100),
    table_y: Optional[float] = Query(default=None, ge=0, le=100),
    table_w: Optional[float] = Query(default=None, ge=0, le=100),
    table_h: Optional[float] = Query(default=None, ge=0, le=100)
):
    """PDF veya görüntüden tablo çıkarır."""
    start_time = time.time()
    
    table_reader = get_table_reader()
    
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Boş dosya")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {str(e)}")
    
    filename = file.filename or ""
    is_pdf = filename.lower().endswith('.pdf') or file.content_type == 'application/pdf'
    
    table_rect = None
    if all(v is not None for v in [table_x, table_y, table_w, table_h]):
        table_rect = {"x": table_x, "y": table_y, "w":  table_w, "h": table_h}
    
    try:
        results = table_reader.extract_tables_from_bytes(
            file_bytes=contents,
            page_number=page_number,
            table_rect=table_rect,
            is_pdf=is_pdf
        )
    except Exception as e:
        logger.error(f"Tablo çıkarma hatası: {e}")
        raise HTTPException(status_code=500, detail=f"Tablo çıkarma hatası: {str(e)}")
    
    tables = []
    total_products = 0
    
    for result in results:
        products = [
            ProductResult(
                ref_number=p.ref_number,
                part_code=p.part_code,
                part_name=p.part_name,
                confidence=p.confidence
            )
            for p in result.products
        ]
        
        tables.append(TableResult(
            table_index=result.table_index,
            row_count=len(result.rows),
            product_count=len(products),
            products=products,
            bbox=result.bbox
        ))
        
        total_products += len(products)
    
    processing_time = (time.time() - start_time) * 1000
    
    return TableExtractionResponse(
        success=True,
        message=f"{len(tables)} tablo, {total_products} ürün bulundu",
        page_number=page_number,
        table_count=len(tables),
        total_products=total_products,
        processing_time_ms=round(processing_time, 2),
        tables=tables
    )


@router.post("/ocr-image", response_model=OcrResponse)
async def ocr_image(
    file: UploadFile = File(..., description="Görüntü dosyası")
):
    """Görüntüden metin çıkarır."""
    start_time = time.time()
    
    table_reader = get_table_reader()
    
    try:
        contents = await file.read()
        if len(contents) == 0:
            raise ValueError("Boş dosya")
        
        import numpy as np
        import cv2
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise ValueError("Görüntü decode edilemedi")
        
        img_height, img_width = image.shape[:2]
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Dosya okunamadı: {str(e)}")
    
    try:
        texts = table_reader.read_text_from_image(image)
    except Exception as e: 
        logger.error(f"OCR hatası: {e}")
        raise HTTPException(status_code=500, detail=f"OCR hatası: {str(e)}")
    
    results = [
        TextResult(
            text=t["text"],
            confidence=t["confidence"],
            bbox=t["bbox"],
            center_x=t["center"]["x"],
            center_y=t["center"]["y"]
        )
        for t in texts
    ]
    
    processing_time = (time.time() - start_time) * 1000
    
    return OcrResponse(
        success=True,
        message=f"{len(results)} metin bulundu",
        text_count=len(results),
        processing_time_ms=round(processing_time, 2),
        image_width=img_width,
        image_height=img_height,
        texts=results
    )


@router.get("/table-info")
async def get_table_service_info():
    """Servis bilgilerini döndürür."""
    try:
        table_reader = get_table_reader()
        return {
            "service":  "PaddleOCR Table Reader",
            "status": "ready",
            "info": table_reader.get_info()
        }
    except HTTPException: 
        return {
            "service": "PaddleOCR Table Reader",
            "status": "not_loaded",
            "info": None
        }