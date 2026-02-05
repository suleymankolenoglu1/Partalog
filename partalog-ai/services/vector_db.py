"""
Partalog AI - Vector Database Service (Smart Filtering v2.0)
Görevi: C#'ın kaydettiği tüm verileri tarar, Python tarafında TEKİLLEŞTİRİR (Deduplication).
Böylece UI için veritabanında çift kayıt tutabiliriz ama Chatbot tek cevap verir.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger
from config import settings
from services.embedding import get_text_embedding 

def get_db_connection():
    """
    Veritabanı bağlantısı oluşturur.
    Config'den gelen 5432 portlu adresi kullanır.
    """
    try:
        conn = psycopg2.connect(
            settings.DB_CONNECTION_STRING,
            cursor_factory=RealDictCursor
        )
        return conn
    except Exception as e:
        logger.error(f"❌ Veritabanı Bağlantı Hatası: {e}")
        # Hata detayını loglayıp fırlatıyoruz ki üst katman sorunu anlasın
        raise e

async def search_parts(query: str, strict_filter: str = None, k: int = 5):
    """
    Kullanıcının sorusunu (query) vektöre çevirir.
    Veritabanından geniş bir havuz çeker (k*4), Python tarafında duplicate'leri temizler.
    """
    conn = None
    try:
        # 1. Metni Vektöre Çevir (Google API)
        query_vector = get_text_embedding(query)
        
        if not query_vector:
            logger.warning("⚠️ Vektör oluşturulamadı (Boş sorgu?), arama atlanıyor.")
            return []

        # 2. Veritabanına Bağlan
        conn = get_db_connection()
        cur = conn.cursor()
        
        # 🔥 STRATEJİ: İstenen sayının (k) 4 katı kadar veri çekelim.
        # Çünkü aralarda çok fazla duplicate (çift) kayıt olabilir (Farklı sayfalardaki aynı parçalar).
        fetch_limit = k * 4 
        
        # SQL Sorgusu (Cosine Similarity - pgvector)
        # PageNumber'ı da çekiyoruz ki debug yaparken hangi sayfadan geldiğini görebilelim.
        sql = """
            SELECT 
                ci."PartCode" as code,
                ci."PartName" as name,
                ci."Description" as desc,
                ci."RefNumber" as ref,
                ci."PageNumber" as page, 
                c."Name" as model,
                1 - (ci."Embedding" <=> %s::vector) as similarity
            FROM "CatalogItems" ci
            LEFT JOIN "Catalogs" c ON ci."CatalogId" = c."Id"
            WHERE 1=1
        """
        params = [query_vector]
        
        # Eğer kullanıcı "parça kodu" gibi kesin bir şey arıyorsa filtrele
        if strict_filter:
            sql += """ AND (ci."PartName" ILIKE %s OR ci."PartCode" ILIKE %s)"""
            params.extend([f"%{strict_filter}%", f"%{strict_filter}%"])
            
        # En benzerleri getir (Limit geniş tutuldu)
        sql += """ ORDER BY ci."Embedding" <=> %s::vector LIMIT %s;"""
        params.extend([query_vector, fetch_limit])
        
        cur.execute(sql, params)
        raw_results = cur.fetchall()
        
        # 3. PYTHON TARAFI FİLTRELEME (Deduplication)
        unique_results = []
        seen_codes = set()
        
        for res in raw_results:
            code = res['code']
            
            # Eğer bu parça kodunu daha önce listeye eklemediysek, ekle.
            if code not in seen_codes:
                unique_results.append(res)
                seen_codes.add(code)
            
            # Yeterli sayıya (k) ulaştıysak dur. Fazlasına gerek yok.
            if len(unique_results) >= k:
                break
                
        return unique_results

    except Exception as e:
        logger.error(f"❌ Vektör Arama Hatası: {e}")
        
        # Sık yapılan hatalar için ipuçları
        err_msg = str(e)
        if 'relation "CatalogItems" does not exist' in err_msg:
            logger.critical("HATA: Tablolar yok! C# tarafında 'Update-Database' yaptın mı?")
        elif 'Connection refused' in err_msg:
            logger.critical("HATA: Veritabanına bağlanılamadı. Docker ayakta mı? Port 5432 doğru mu?")
            
        return []
    finally:
        # Bağlantıyı her zaman kapat (Memory Leak önlemi)
        if conn:
            conn.close()