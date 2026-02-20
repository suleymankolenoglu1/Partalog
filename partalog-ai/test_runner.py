import asyncio
import os
import json
from PIL import Image
from dotenv import load_dotenv

# visual_ingest.py dosyanın 'api' klasöründe olduğunu varsayıyorum.
# Eğer ana dizindeyse: "from visual_ingest import hybrid_pipeline" yap.
try:
    from api.visual_ingest import hybrid_pipeline
except ImportError:
    # Eğer dosya ana dizindeyse
    from visual_ingest import hybrid_pipeline

# .env dosyasını yükle (API Key için)
load_dotenv()

async def run_test():
    image_path = "test_page.jpg"
    
    if not os.path.exists(image_path):
        print(f"❌ HATA: '{image_path}' dosyası bulunamadı! Lütfen proje klasörüne bir test resmi koy.")
        return

    print(f"🚀 Test Başlıyor: {image_path}")
    print("⏳ Motor ısınıyor (Pipeline çalışıyor)...")

    try:
        # Resmi yükle
        img = Image.open(image_path).convert("RGB")
        
        # Pipeline'ı direkt çağır (HTTP yok, Frontend yok)
        results = await hybrid_pipeline(img)

        print("\n" + "="*50)
        print(f"✅ SONUÇ: {len(results)} parça bulundu!")
        print("="*50)
        
        # JSON çıktısını ekrana bas
        print(json.dumps(results, indent=2, ensure_ascii=False))
        
        print("\n📂 Lütfen 'debug_dumps' klasörünü kontrol et.")
        print("   Orada 'final_XX.jpg' resimlerini görmelisin.")

    except Exception as e:
        print(f"\n💥 PATLADI: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Async fonksiyonu çalıştır
    asyncio.run(run_test())