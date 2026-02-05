import asyncio
from services.vector_db import search_parts
from loguru import logger

# Logları görelim
logger.remove()
logger.add(lambda msg: print(msg, end=""), format="{message}", level="INFO")

async def test():
    print("\n🔎 TEST 1: 'Lower Knife' araması yapılıyor...")
    # İngilizce soralım, çünkü veritabanı İngilizce (Semantic search yine de bulmalı)
    results = await search_parts("Lower Knife", k=10) # Limiti 10 yaptık
    
    print(f"\nSonuç Sayısı: {len(results)}")
    for i, res in enumerate(results):
        # Benzerlik skoru 1'e ne kadar yakınsa o kadar iyi
        score = res.get('similarity', 0)
        name = res.get('name')
        code = res.get('code')
        desc = res.get('desc')
        print(f"{i+1}. [{score:.4f}] {code} - {name} ({desc})")

    print("\n" + "="*50 + "\n")

    print("🔎 TEST 2: 'hareketli bıçak' (Türkçe) araması yapılıyor...")
    results_tr = await search_parts("hareketli bıçak", k=10)
    
    for i, res in enumerate(results_tr):
        score = res.get('similarity', 0)
        name = res.get('name')
        code = res.get('code')
        print(f"{i+1}. [{score:.4f}] {code} - {name}")

if __name__ == "__main__":
    asyncio.run(test())