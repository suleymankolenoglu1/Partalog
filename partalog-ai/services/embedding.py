import requests
from fastapi import HTTPException
from loguru import logger
from config import settings
import os

def get_text_embedding(text: str):
    """
    Verilen metni Google Gemini 'text-embedding-004' modelini kullanarak
    768 boyutlu bir vektöre çevirir.
    """
    # API Key Config'den veya Environment'tan alınır
    api_key = getattr(settings, "GEMINI_API_KEY", os.getenv("GEMINI_API_KEY"))
    
    if not api_key:
        logger.error("GEMINI_API_KEY bulunamadı!")
        return None

    model_name = "models/text-embedding-004"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:embedContent?key={api_key}"
    
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

        return vector

    except Exception as e:
        logger.error(f"Embedding Bağlantı Hatası: {str(e)}")
        return None