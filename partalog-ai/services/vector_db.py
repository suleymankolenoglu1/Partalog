import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger
from config import settings
from services.embedding import get_text_embedding 

def get_db_connection():
    try:
        return psycopg2.connect(
            settings.DB_CONNECTION_STRING,
            cursor_factory=RealDictCursor
        )
    except Exception as e:
        logger.error(f"Veritabanı Bağlantı Hatası: {e}")
        raise e

async def search_parts(query: str, strict_filter: str = None, k: int = 5):
    try:
        # 1. Metni Vektöre Çevir
        query_vector = get_text_embedding(query)
        
        if not query_vector:
            logger.warning("Vektör oluşturulamadı, arama atlanıyor.")
            return []

        conn = get_db_connection()
        cur = conn.cursor()
        
        # 🔥 C# ENTITY YAPISINA GÖRE GÜNCELLENMİŞ SQL 🔥
        # Tablo: "CatalogItems" (Entity Framework çoğul yapar)
        # Sütunlar: "PartCode", "PartName", "Description", "RefNumber"
        # Model Adı için "Catalogs" tablosuna JOIN atıyoruz.
        
        sql = """
            SELECT 
                ci."PartCode" as code,         -- C#: PartCode
                ci."PartName" as name,         -- C#: PartName
                ci."Description" as desc,      -- C#: Description
                ci."RefNumber" as ref,         -- C#: RefNumber (Referans No)
                c."Name" as model,             -- Catalogs tablosundan makine adı (Varsayım: Name sütunu)
                1 - (ci."Embedding" <=> %s::vector) as similarity
            FROM "CatalogItems" ci
            LEFT JOIN "Catalogs" c ON ci."CatalogId" = c."Id"
            WHERE 1=1
        """
        params = [query_vector]
        
        if strict_filter:
            # Hem kodda hem isimde ara
            sql += """ AND (ci."PartName" ILIKE %s OR ci."PartCode" ILIKE %s)"""
            params.extend([f"%{strict_filter}%", f"%{strict_filter}%"])
            
        sql += """ ORDER BY ci."Embedding" <=> %s::vector LIMIT %s;"""
        params.extend([query_vector, k])
        
        cur.execute(sql, params)
        results = cur.fetchall()
        
        cur.close()
        conn.close()
        
        return results

    except Exception as e:
        logger.error(f"Vector DB Arama Hatası: {e}")
        
        # Olası hataları loga basıp ipucu verelim
        err_msg = str(e)
        if 'relation "CatalogItems" does not exist' in err_msg:
            logger.error("HATA: 'CatalogItems' tablosu bulunamadı. EF Core migration yaptınız mı?")
        elif 'column c.Name does not exist' in err_msg:
            logger.error("HATA: Catalogs tablosunda 'Name' sütunu yok. O tablodaki ad sütunu farklı olabilir (örn: Title, ModelName).")
            
        return []