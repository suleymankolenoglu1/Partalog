import os
from dotenv import load_dotenv
import google.generativeai as genai

# 1. .env dosyasını yükle
load_dotenv()

# 2. API Key'i "GOOGLE_API_KEY" adıyla al (.env dosyasındaki ismin bu olduğu için)
raw_api_key = os.getenv("GOOGLE_API_KEY")

if not raw_api_key:
    print("❌ HATA: GOOGLE_API_KEY bulunamadı! .env dosyanı kontrol et.")
    exit()

# 3. TIRNAK TEMİZLİĞİ (Kritik Adım 🛠️)
# .env dosyasında "AIza..." şeklinde tırnak varsa onları siliyoruz.
api_key = raw_api_key.replace('"', '').replace("'", '').strip()

print(f"✅ Key Alındı ve Temizlendi: {api_key[:5]}... (Tırnaksız)")

# 4. Gemini'yi yapılandır
genai.configure(api_key=api_key)

print("\n--- Müsait Embedding Modelleri ---")
try:
    found_models = []
    for m in genai.list_models():
        if 'embed' in m.name:
            print(f"📦 Model: {m.name}")
            found_models.append(m.name)
            
    if not found_models:
        print("⚠️ Hiçbir embedding modeli bulunamadı. API Key yetkilerini kontrol et.")
        
except Exception as e:
    print(f"🔥 Bir hata oluştu: {e}")