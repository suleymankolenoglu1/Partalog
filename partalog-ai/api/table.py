# api/table.py

from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from loguru import logger
import time

# main.py'den modelleri çekmek için (Adım 4'te orayı ayarlayacağız)
from core.dependencies import get_ai_engine


router = APIRouter()

# --- Schemas (Frontend bozulmasın diye aynı yapıyı koruyoruz) ---

class ProductResult(BaseModel):
    ref_number: int = Field(default=0)
    part_code: str
    part_name: str
    quantity: int = Field(default=1)
    confidence: float = Field(default=0.99) # Gemini güven skoru vermez, varsayılan atıyoruz

class TableResult(BaseModel):
    table_index: int = 0
    row_count: int
    product_count: int
    products: List[ProductResult]
    bbox: Optional[List[float]] = None

class TableExtractionResponse(BaseModel):
    success: bool
    message: str
    page_number: int
    total_products: int
    processing_time_ms: float
    tables: List[TableResult]

# --- Endpoint ---

@router.post("/extract-table", response_model=TableExtractionResponse)
async def extract_table(
    file: UploadFile = File(...),
    page_number: int = Query(default=1),
    # Dependency Injection ile motoru alıyoruz
    engine = Depends(get_ai_engine) 
):
    start_time = time.time()
    
    # 1. Dosyayı Oku
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Dosya boş")

    # 2. Gemini'ye Gönder
    try:
        # ai_engine.py içindeki metod
        raw_data = engine.extract_table(content)
    except Exception as e:
        logger.error(f"AI Engine Error: {e}")
        raise HTTPException(status_code=500, detail="AI motoru hatası")

    # 3. Veriyi Modele Dönüştür
    products = []
    for item in raw_data:
        # Güvenli tip dönüşümü
        try:
            p = ProductResult(
                ref_number=int(item.get("ref_number", 0) or 0),
                part_code=str(item.get("part_code", "")).strip(),
                part_name=str(item.get("part_name", "")).strip(),
                quantity=int(item.get("quantity", 1) or 1)
            )
            products.append(p)
        except:
            continue

    # 4. Yanıtı Hazırla
    duration = (time.time() - start_time) * 1000
    
    table_result = TableResult(
        row_count=len(products),
        product_count=len(products),
        products=products
    )

    return TableExtractionResponse(
        success=True,
        message=f"Gemini {len(products)} parça buldu.",
        page_number=page_number,
        total_products=len(products),
        processing_time_ms=round(duration, 2),
        tables=[table_result]
    )