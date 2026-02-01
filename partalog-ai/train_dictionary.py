import os
import json
import time
import pandas as pd
import google.generativeai as genai
from sqlalchemy import create_engine
from config import settings  # API KEY'in config.py içinde olduğu varsayılıyor

# ==========================================
# ⚙️ AYARLAR (Senin Bilgilerinle Güncellendi)
# ==========================================

# Format: postgresql://kullanici:sifre@host:port/veritabani
# Senin Portun: 5435 (Standart 5432 değil, dikkat ettim)
DB_CONNECTION_STRING = "postgresql://postgres:Password123!@localhost:5435/KatalogcuDb"

BATCH_SIZE = 40           # Gemini'ye tek seferde sorulacak kelime sayısı
OUTPUT_FILE = "sanayi_sozlugu.json"  # Sözlüğün kaydedileceği dosya

# Gemini Konfigürasyonu
try:
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-lite') 
except Exception as e:
    print(f"⚠️ API Key Hatası: {e}")
    print("Lütfen config.py dosyasında GEMINI_API_KEY olduğundan emin ol.")
    exit()

# ==========================================
# 🛠️ FONKSİYONLAR
# ==========================================

def get_db_terms():
    """Veritabanındaki tüm benzersiz İngilizce parça isimlerini çeker."""
    print("🔌 Veritabanına bağlanılıyor...")
    try:
        engine = create_engine(DB_CONNECTION_STRING)
        
        # Sadece İngilizce adı dolu olanları ve kısa olmayanları çekiyoruz
        query = """
        SELECT DISTINCT "PartName" 
        FROM "CatalogItems" 
        WHERE "PartName" IS NOT NULL 
        AND LENGTH("PartName") > 2
        """
        
        df = pd.read_sql(query, engine)
        
        # Veriyi temizle ve listeye çevir
        terms_list = df['PartName'].str.strip().str.upper().unique().tolist()
        print(f"📊 Veritabanında toplam {len(terms_list)} adet benzersiz parça ismi bulundu.")
        return set(terms_list)
    except Exception as e:
        print(f"❌ Veritabanı Bağlantı Hatası: {e}")
        print("Lütfen connection string'i ve veritabanının ayakta olduğunu kontrol et.")
        return set()

def load_existing_dictionary():
    """Mevcut JSON sözlüğünü yükler."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"📚 Mevcut hafıza yüklendi: {len(data)} kelime biliniyor.")
            return data
        except Exception as e:
            print(f"⚠️ Dosya okuma hatası, sıfırdan başlanıyor: {e}")
            return {}
    return {}

def ask_gemini_batch(terms_batch):
    """Gemini'ye sanayi argosunu sorar."""
    
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
        clean_text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_text)
    except Exception as e:
        print(f"⚠️ API/Parsing Hatası (Bu grup atlanıyor): {e}")
        return {}

# ==========================================
# 🚀 ANA AKIŞ
# ==========================================
def main():
    print("--- 🧠 PARTALOG AI SÖZLÜK EĞİTİMİ BAŞLIYOR ---")

    # 1. Verileri Hazırla
    existing_dict = load_existing_dictionary() 
    db_terms_set = get_db_terms()              
    
    if not db_terms_set:
        print("❌ Veritabanından veri çekilemedi. İşlem iptal.")
        return

    known_terms_set = set(existing_dict.keys()) 

    # 2. Fark Analizi (Yeni Kelimeler)
    new_terms_to_learn = list(db_terms_set - known_terms_set)
    count_new = len(new_terms_to_learn)

    if count_new == 0:
        print("\n✅ SİSTEM ZATEN GÜNCEL! Öğrenilecek yeni kelime yok.")
        return

    print(f"\n🚀 TESPİT EDİLDİ: {count_new} adet yeni kelime öğrenilecek.")
    print("☕ Kahveni al, Gemini ustalarla görüşmeye başlıyor...\n")

    # 3. Öğrenme Döngüsü
    newly_learned_data = {}
    total_batches = (count_new // BATCH_SIZE) + 1
    
    for i in range(0, count_new, BATCH_SIZE):
        batch = new_terms_to_learn[i:i + BATCH_SIZE]
        current_batch_num = (i // BATCH_SIZE) + 1
        
        print(f"⏳ [{current_batch_num}/{total_batches}] İşleniyor: {batch[:3]}... (+{len(batch)-3} adet)")
        
        batch_result = ask_gemini_batch(batch)
        
        if batch_result:
            newly_learned_data.update(batch_result)
            print(f"   ✅ {len(batch_result)} kelime öğrenildi.")
        else:
            print("   ⚠️ Cevap alınamadı, pas geçiliyor.")

        time.sleep(1.5) # API Rate Limit koruması

    # 4. Kaydetme
    if newly_learned_data:
        print("\n💾 Yeni bilgiler hafızaya işleniyor...")
        existing_dict.update(newly_learned_data)
        
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing_dict, f, ensure_ascii=False, indent=4)
        
        print(f"🎉 İŞLEM TAMAMLANDI! Toplam Bilgi: {len(existing_dict)} kelime.")
    else:
        print("\n⚠️ Yeni veri öğrenilemedi (Hata oluşmuş olabilir).")

if __name__ == "__main__":
    main()