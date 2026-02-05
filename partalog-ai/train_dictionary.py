"""
Partalog AI - Sanayi Sözlüğü Eğitmeni (Auto-Trainer)
Görevi: Veritabanındaki yeni İngilizce parça isimlerini bulur ve
Gemini'ye "Sanayide buna ne denir?" diye sorarak sözlüğü günceller.
"""

import os
import json
import time
import pandas as pd
import google.generativeai as genai
from sqlalchemy import create_engine
from config import settings # <--- AYARLARI BURADAN ÇEKİYORUZ
from loguru import logger

# ==========================================
# ⚙️ AYARLAR
# ==========================================

# DB Bağlantısı (Artık config dosyasından geliyor)
DB_CONNECTION_STRING = settings.DB_CONNECTION_STRING

BATCH_SIZE = 40           # Gemini'ye tek seferde sorulacak kelime sayısı
OUTPUT_FILE = "sanayi_sozlugu.json"

# Gemini Konfigürasyonu
model = None
try:
    if not settings.GEMINI_API_KEY:
        logger.warning("⚠️ [EĞİTİM] API Key bulunamadı (settings.GEMINI_API_KEY boş). Eğitim yapılamayacak.")
    else:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-2.0-flash-lite') 
except Exception as e:
    logger.critical(f"⚠️ [EĞİTİM] Gemini Başlatma Hatası: {e}")

# ==========================================
# 🛠️ FONKSİYONLAR
# ==========================================

def get_db_terms():
    """Veritabanındaki tüm benzersiz İngilizce parça isimlerini çeker."""
    logger.info(f"🔌 [EĞİTİM] Veritabanına bağlanılıyor... (Host: {DB_CONNECTION_STRING.split('@')[-1]})")
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        
        # Sadece İngilizce adı dolu olanları ve kısa olmayanları çekiyoruz (En az 3 harf)
        query = """
        SELECT DISTINCT "PartName" 
        FROM "CatalogItems" 
        WHERE "PartName" IS NOT NULL 
        AND LENGTH("PartName") > 2
        """
        
        df = pd.read_sql(query, engine)
        
        # Veriyi temizle ve listeye çevir (Büyük harf yap)
        terms_list = df['PartName'].str.strip().str.upper().unique().tolist()
        logger.info(f"📊 [EĞİTİM] Veritabanında toplam {len(terms_list)} adet benzersiz parça ismi bulundu.")
        return set(terms_list)
    except Exception as e:
        logger.error(f"❌ [EĞİTİM] Veritabanı Bağlantı Hatası: {e}")
        logger.warning("💡 İPUCU: 'config.py' veya '.env' dosyasındaki DB bağlantı adresini kontrol et.")
        return set()

def load_existing_dictionary():
    """Mevcut JSON sözlüğünü yükler."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            logger.info(f"📚 [EĞİTİM] Mevcut hafıza yüklendi: {len(data)} kelime biliniyor.")
            return data
        except Exception as e:
            logger.error(f"⚠️ [EĞİTİM] Dosya okuma hatası, sıfırdan başlanıyor: {e}")
            return {}
    return {}

def ask_gemini_batch(terms_batch):
    """Gemini'ye sanayi argosunu sorar."""
    
    if not model:
        logger.error("❌ [EĞİTİM] Model başlatılamadığı için sorgu yapılamıyor.")
        return {}

    prompt = f"""
    Sen Türkiye sanayisinde (tekstil makineleri) uzmanlaşmış bir usta başısın.
    Aşağıdaki İngilizce teknik parça isimlerinin, Türkiye sanayisinde kullanılan "Usta Argosu" (Jargon) karşılıklarını ver.
    
    Kurallar:
    1. Resmi sözlük çevirisi yapma. Ustalar ne diyorsa onu yaz.
       - Örn: "THREAD STAND" -> "Çardak" (İplik standı deme)
       - Örn: "LOOPER" -> "Lüper"
       - Örn: "NEEDLE BAR" -> "İğne Mili"
       - Örn: "HEX SOCKET SCREW" -> "Alyan Vida", "İmbus"
    2. Eğer bir karşılığı yoksa, Türkçeleşmiş halini yaz (Örn: "Bracket" -> "Braket").
    3. Çıktıyı SADECE JSON formatında ver. Başka hiçbir şey yazma.

    Terim Listesi:
    {json.dumps(terms_batch)}

    Beklenen JSON Formatı:
    {{
        "ENGLISH TERM": ["Türkçe Jargon 1", "Alternatif Jargon"],
        "ANOTHER TERM": ["Tek Karşılık"]
    }}
    """

    try:
        response = model.generate_content(prompt)
        text = response.text
        # JSON temizliği (Markdown taglerini temizle)
        clean_text = text.replace("```json", "").replace("```", "").strip()
        
        # Bazen Gemini JSON'ın sonuna fazladan karakter koyabilir, basit temizlik
        if not clean_text.endswith("}"):
             clean_text = clean_text[:clean_text.rfind("}")+1]

        return json.loads(clean_text)
    except Exception as e:
        logger.warning(f"⚠️ [EĞİTİM] API/Parsing Hatası (Bu grup atlanıyor): {e}")
        return {}

# ==========================================
# 🚀 ANA AKIŞ (main.py tarafından çağrılır)
# ==========================================
def main():
    logger.info("--- 🧠 PARTALOG AI SÖZLÜK EĞİTİMİ BAŞLIYOR (AUTO) ---")

    # 1. Verileri Hazırla
    existing_dict = load_existing_dictionary() 
    db_terms_set = get_db_terms()              
    
    if not db_terms_set:
        logger.error("❌ [EĞİTİM] Veritabanından veri çekilemedi veya veritabanı boş. İşlem iptal.")
        return

    known_terms_set = set(existing_dict.keys()) 

    # 2. Fark Analizi (Yeni Kelimeler)
    new_terms_to_learn = list(db_terms_set - known_terms_set)
    count_new = len(new_terms_to_learn)

    if count_new == 0:
        logger.success("✅ [EĞİTİM] SİSTEM ZATEN GÜNCEL! Öğrenilecek yeni kelime yok.")
        return

    logger.info(f"🚀 [EĞİTİM] TESPİT EDİLDİ: {count_new} adet yeni kelime öğrenilecek.")
    logger.info("☕ Kahveni al, Gemini ustalarla görüşmeye başlıyor...")

    # 3. Öğrenme Döngüsü
    newly_learned_data = {}
    total_batches = (count_new // BATCH_SIZE) + 1
    
    for i in range(0, count_new, BATCH_SIZE):
        batch = new_terms_to_learn[i:i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1
        
        logger.info(f"⏳ [EĞİTİM] Batch [{current_batch_num}/{total_batches}] İşleniyor... ({len(batch)} adet)")
        
        batch_result = ask_gemini_batch(batch)
        
        if batch_result:
            newly_learned_data.update(batch_result)
            logger.info(f"   ✅ {len(batch_result)} kelime hafızaya alındı.")
        else:
            logger.warning("   ⚠️ Cevap alınamadı, pas geçiliyor.")

        time.sleep(1.5) # API Rate Limit koruması

    # 4. Kaydetme
    if newly_learned_data:
        logger.info("💾 [EĞİTİM] Yeni bilgiler diske yazılıyor...")
        existing_dict.update(newly_learned_data)
        
        try:
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing_dict, f, ensure_ascii=False, indent=4)
            
            logger.success(f"🎉 [EĞİTİM] İŞLEM TAMAMLANDI! Toplam Sözlük Bilgisi: {len(existing_dict)} kelime.")
        except Exception as e:
            logger.error(f"❌ [EĞİTİM] Dosya yazma hatası: {e}")
    else:
        logger.warning("⚠️ [EĞİTİM] Yeni veri öğrenilemedi (Hata oluşmuş olabilir).")

# Eğer dosya doğrudan terminalden çalıştırılırsa
if __name__ == "__main__":
    main()