"""
Partalog AI - TEST SEARCH (Filtreli Arama)
Görevi: Yapay zekanın "İğne" getirmesini engelleyip sadece "Vida" getirmesini sağlamak.
"""

import asyncio
from services.vector_db import search_parts

async def test_hybrid_search():
    # Senaryo: Kullanıcı "Juki Reçme Vida" dedi.
    user_query = "Juki coverstitch screw" 
    
    print(f"🔍 SORGULANIYOR: '{user_query}'")
    print("-" * 50)

    # ❌ YANLIŞ YÖNTEM (Sadece Vektör):
    # Bu, senin az önce yaşadığın sorunu yaratır. Ne bulursa getirir.
    print("1️⃣ FİLTRESİZ ARAMA (Eski Hatalı Yöntem):")
    results_raw = await search_parts(user_query, k=5)
    for r in results_raw:
        print(f"   - {r['code']} | {r['name']} ({r['similarity']:.4f})")
    
    print("\n" + "="*50 + "\n")

    # ✅ DOĞRU YÖNTEM (Hibrit Arama):
    # Chatbot, kullanıcının "Vida" dediğini anlayıp, veritabanına "SCREW" filtresi yollar.
    print("2️⃣ FİLTRELİ ARAMA (Hybrid Search - Jilet Gibi):")
    
    # strict_filter="SCREW" gönderiyoruz. 
    # Bu sayede veritabanı; vektör uyuşsa bile içinde "SCREW" yazmayanları ÇÖPE ATAR.
    results_filtered = await search_parts(user_query, strict_filter="SCREW", k=5)
    
    for r in results_filtered:
        print(f"   - {r['code']} | {r['name']} ({r['dimensions'] if 'dimensions' in r else ''})")

if __name__ == "__main__":
    asyncio.run(test_hybrid_search())