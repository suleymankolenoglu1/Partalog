import requests
from loguru import logger
from config import settings
import os

def get_text_embedding(text: str):
    """
    Verilen metni Google Gemini 'gemini-embedding-001' modelini kullanarak vektöre çevirir.
    Veritabanı 3072 boyutuna güncellendiği için veri olduğu gibi (RAW) iletilir.
    """
    
    # 1. API Key Alma
    raw_api_key = getattr(settings, "GOOGLE_API_KEY", None) or \
                  os.getenv("GOOGLE_API_KEY") or \
                  getattr(settings, "GEMINI_API_KEY", None) or \
                  os.getenv("GEMINI_API_KEY")
    
    if not raw_api_key:
        logger.error("API Key bulunamadı!")
        return None

    api_key = raw_api_key.replace('"', '').replace("'", '').strip()

    # Model Adı
    model_name = "models/gemini-embedding-001"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:embedContent?key={api_key}"
    
    # 2. PAYLOAD (Parametre yok, sınırlama yok. Ne varsa gelsin.)
    payload = {
        "model": model_name,
        "content": {"parts": [{"text": text}]}
    }
    
    try:
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
        
        if response.status_code != 200:
            logger.error(f"Gemini Embedding API Hatası: {response.text}")
            return None

        data = response.json()
        vector = data.get("embedding", {}).get("values")
        
        if not vector:
            logger.error("API boş vektör döndü.")
            return None

        # 3. KONTROL MEKANİZMASI (Sadece Loglama)
        # Artık hata verip durdurmuyoruz. 3072 gelirse "Başım üstüne" diyoruz.
        vec_len = len(vector)
        
        # Eğer çok küçük bir vektör gelirse (örn: hatalı bir durum) uyaralım ama yine de dönelim.
        if vec_len < 768:
             logger.warning(f"⚠️ Dikkat: Vektör boyutu beklenenden küçük geldi: {vec_len}")
        
        # Veritabanı 3072 olduğu için, 3072 gelen veriyi olduğu gibi yolluyoruz.
        return vector

    except Exception as e:
        logger.error(f"Embedding Bağlantı Hatası: {str(e)}")
        return None