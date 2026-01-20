# core/ai_engine.py

import os
import json
import base64
import requests
from loguru import logger
from dotenv import load_dotenv

# .env yükle
load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

class GeminiTableExtractor:
    def __init__(self):
        if not GOOGLE_API_KEY:
            logger.critical("❌ GOOGLE_API_KEY bulunamadı! .env dosyasını kontrol et.")
            raise ValueError("Google API Key eksik.")
        
        # --- DÜZELTME BURADA ---
        # "gemini-2.0-flash" (Limit 0 hatası verdi) yerine
        # Listenizdeki "JOKER" modeli kullanıyoruz. 
        # Bu model her zaman erişilebilir olan en güncel Flash sürümüdür.
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GOOGLE_API_KEY}"
        
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        logger.info("✅ Gemini Flash Latest (Joker Model) başlatıldı.")

    def extract_table(self, image_bytes: bytes) -> list:
        try:
            # 1. Görüntüyü Base64'e çevir
            b64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            # 2. İstek Gövdesi
            payload = {
                "contents": [{
                    "parts": [
                        {"text": """
                        Analyze this spare parts catalog page. Extract the main table into a JSON list.
                        Keys per item:
                        - "ref_number": (int) Reference No. If empty, try to infer.
                        - "part_code": (string) Part Number. MUST be uppercase alphanumeric. Remove noise.
                        - "part_name": (string) Description.
                        - "quantity": (int) Qty. 'l' or '|' = 1.
                        
                        Rules:
                        1. Return ONLY the raw JSON list.
                        2. No markdown.
                        """},
                        {
                            "inline_data": {
                                "mime_type": "image/jpeg", 
                                "data": b64_image
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "temperature": 0.0,
                    "response_mime_type": "application/json"
                }
            }

            # 3. İsteği Gönder
            response = self.session.post(
                self.api_url,
                json=payload,
                timeout=45
            )

            # 4. Hata Kontrolü
            if response.status_code != 200:
                logger.error(f"Google API Hatası ({response.status_code}): {response.text}")
                return []
            
            # 5. JSON Parse
            result = response.json()
            try:
                if 'candidates' in result and result['candidates']:
                    text_content = result['candidates'][0]['content']['parts'][0]['text']
                    return json.loads(text_content)
                return []
            except Exception as e:
                logger.warning(f"JSON Parse edilemedi: {e}")
                return []

        except Exception as e:
            logger.error(f"Sistem Hatası: {e}")
            return []