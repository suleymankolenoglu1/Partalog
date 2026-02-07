"""
Partalog AI - Vector Database Service (Async/Pgvector/3072)
---------------------------------------------------------
Görevi: C# tarafından oluşturulan 3072'lik vektörleri okumak ve aramak.
"""

import asyncpg
import json
from loguru import logger
from config import settings

async def get_db_connection():
    """
    Asenkron veritabanı bağlantısı (asyncpg).
    Config dosyasındaki farklı isimlendirmeleri (DB_CONNECTION_STRING veya DATABASE_URL) yönetir.
    """
    try:
        # 1. Önce senin muhtemel ayar ismini deneriz
        dsn = getattr(settings, "DB_CONNECTION_STRING", None)
        
        # 2. Bulamazsa standart ismi deneriz
        if not dsn:
            dsn = getattr(settings, "DATABASE_URL", None)
            
        if not dsn:
            logger.critical("❌ HATA: Config dosyasında Veritabanı Bağlantı Linki bulunamadı!")
            return None

        # Bağlantıyı kur
        return await asyncpg.connect(dsn)

    except Exception as e:
        logger.error(f"❌ Veritabanı Bağlantı Hatası: {e}")
        return None

async def search_vector_db(query_vector: list, brand_filter: str = None, limit: int = 5):
    """
    Vektörel benzerlik araması yapar.
    
    Args:
        query_vector (list): 3072 boyutlu float listesi.
        brand_filter (str): Marka filtresi (Opsiyonel).
        limit (int): Sonuç sayısı.
    """
    conn = await get_db_connection()
    if not conn:
        return []

    try:
        # 1. Boyut Güvenlik Kontrolü (3072)
        if len(query_vector) != 3072:
            logger.warning(f"⚠️ Vektör boyutu 3072 değil! Gelen: {len(query_vector)}")

        # 2. SQL Sorgusu (Cosine Similarity: <=>)
        # asyncpg'de parametreler $1, $2 diye gider.
        sql = """
            SELECT 
                "Id",
                "PartCode",
                "PartName",
                "MachineBrand",
                "MachineModel", 
                "MachineGroup",
                "Description",
                "Dimensions",
                1 - ("Embedding" <=> $1) as similarity
            FROM "CatalogItems"
            WHERE 1=1
        """
        
        # pgvector için vektörü string formatında gönderiyoruz '[0.1, 0.2...]'
        params = [str(query_vector)]
        param_idx = 2

        # 3. Marka Filtresi (Varsa)
        if brand_filter:
            sql += f" AND \"MachineBrand\" ILIKE ${param_idx}"
            params.append(f"%{brand_filter}%")
            param_idx += 1
            
        # 4. Sıralama ve Limit
        sql += f" ORDER BY similarity DESC LIMIT ${param_idx}"
        params.append(limit)

        # 5. Çalıştır
        results = await conn.fetch(sql, *params)
        
        # Sonuçları Dictionary listesine çevir
        return [dict(row) for row in results]

    except Exception as e:
        logger.error(f"❌ Vektör Arama Hatası: {e}")
        return []
    finally:
        if conn:
            await conn.close()