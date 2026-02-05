import pandas as pd
from sqlalchemy import create_engine
import sys

# Senin bağlantı adresin (Port 5435)
DB_STRING = "postgresql://postgres:Password123!@localhost:5435/KatalogcuDb"

# 🛠️ PANDAS AYARLARI: "Sakın kısaltma yapma, hepsini göster" diyoruz
pd.set_option('display.max_rows', None)      # Satır limiti yok
pd.set_option('display.max_columns', None)   # Sütun limiti yok
pd.set_option('display.width', None)         # Genişlik limiti yok
pd.set_option('display.max_colwidth', None)  # Hücre içi kesme yok

try:
    print("🔌 Veritabanına bağlanılıyor ve TÜM parçalar çekiliyor...")
    engine = create_engine(DB_STRING)
    
    # 🔍 SORGUNUN MANTIĞI:
    # DISTINCT: Aynı isimden 100 tane varsa sadece 1 tanesini getir (Benzersizlik).
    # ORDER BY: A'dan Z'ye sırala.
    query = """
    SELECT DISTINCT "PartName" 
    FROM "CatalogItems" 
    WHERE "PartName" IS NOT NULL 
    AND LENGTH("PartName") > 1
    ORDER BY "PartName" ASC;
    """
    
    df = pd.read_sql(query, engine)
    total_count = len(df)
    
    print(f"\n📊 Veritabanında Toplam {total_count} adet BENZERSİZ Parça İsmi bulundu.\n")
    print("=" * 60)
    
    # 1. EKRANA BAS (Tüm Liste)
    # df.to_string() metodu dataframe'i saf string'e çevirir, tablo formatını korur.
    print(df["PartName"].to_string(index=True))
    
    print("=" * 60)
    
    # 2. DOSYAYA KAYDET (Garanti olsun)
    filename = "tum_benzersiz_parcalar.txt"
    with open(filename, "w", encoding="utf-8") as f:
        # Başlık
        f.write(f"--- TOPLAM {total_count} ADET BENZERSİZ PARÇA ---\n\n")
        # Listeyi yaz
        for index, row in df.iterrows():
            f.write(f"{row['PartName']}\n")
            
    print(f"\n✅ Tüm liste '{filename}' dosyasına kaydedildi.")
    
    # 3. ÖZEL KONTROL (Senin aradığın kritik kelimeler)
    print("\n🔍 KRİTİK KELİME KONTROLÜ (SOLENOID / KNIFE / VALVE):")
    target_words = ["SOLENOID", "KNIFE", "VALVE"]
    
    # Tüm listeyi büyük harfe çevirip tek bir metin yapalım ki araması kolay olsun
    all_text_blob = " ".join(df["PartName"].astype(str).tolist()).upper()
    
    found_any = False
    for word in target_words:
        if word in all_text_blob:
            print(f"   ✅ '{word}' kelimesi veritabanında VAR.")
            found_any = True
        else:
            print(f"   ❌ '{word}' kelimesi veritabanında YOK.")
            
    if not found_any:
        print("\n🚨 SONUÇ: Yeni katalogdaki parçalar PostgreSQL'e GİRMEMİŞ.")

except Exception as e:
    print(f"💥 HATA: {e}")