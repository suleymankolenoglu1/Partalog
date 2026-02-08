"""
Partalog AI - Chat API (Final v4.2 - Turkish Native Mode 🇹🇷)
------------------------------------------------
1. NO DICTIONARY: Sözlük iptal. "SCREW" yok, "VİDA" var.
2. NATIVE SEARCH: Kullanıcı ne derse o aranır (3072 Vektör).
3. SMART ROUTER: Marka ve Parça ismini ayıklar.
4. MULTI-PART: Birden fazla parça istenirse "parts" listesi döndürür.
"""

import aiohttp
import json
import urllib.parse
from fastapi import APIRouter, Form
from loguru import logger
from config import settings

# ✅ Gerekli Servisler
from services.embedding import get_text_embedding 
from services.vector_db import search_vector_db 

router = APIRouter()

# ⚡️ Gemini API
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"
SHOP_BASE_URL = "https://www.parcagalerisi.com/ara/"

# =========================================================
# 🕵️‍♂️ ROUTER: NİYET VE PARÇA ANALİZİ (TÜRKÇE)
# =========================================================
async def analyze_intent_with_gemini(text: str) -> dict:
    """
    Kullanıcı mesajını analiz eder.
    AMACIMIZ: Markayı ve Aranacak 'Saf Türkçe' parça ismini bulmak.
    """
    system_prompt = """
    GÖREV: Bir sanayi yedek parça asistanı olarak kullanıcı mesajını analiz et.
    
    ÇIKTI FORMATI (JSON):
    {
        "intent": "SEARCH" | "CHAT" | "PRICE" | "STOCK" | "COMPATIBILITY" | "HELP" | "COMPARE",
        "brand": "Marka Varsa Buraya (TYPICAL, JUKI, YAMATO, PEGASUS, BROTHER...)",
        "part_name": "Aranan Parçanın SAF TÜRKÇE ADI (Sıfatları at, kök ismi bul)",
        "part_code": "Parça kodu varsa buraya (örn: B2424-354-000)",
        "parts": [
          {"part_name": "...", "part_code": null},
          {"part_name": "...", "part_code": null}
        ],
        "machine_group": "Makine Grubu (Reçme, Overlok, Düz...)",
        "confidence": 0.0-1.0 arasında bir güven skoru
    }

    KURALLAR:
    1. ASLA İngilizceye çevirme. Kullanıcı "Vida" dediyse "VİDA" al. "SCREW" DEME!
    2. Gereksiz kelimeleri at ("var mı", "fiyatı ne", "lazım", "acaba", "bulabilir misin").
    3. Birden fazla parça varsa "parts" listesine hepsini koy.
       - Tek parça varsa bile parts[0] doldur.
    4. KULLANIM:
       - Eğer fiyat soruluyorsa intent = "PRICE"
       - Eğer stok soruluyorsa intent = "STOCK"
       - Eğer uyumluluk soruluyorsa intent = "COMPATIBILITY"
       - Eğer açıklama/yardım isteniyorsa intent = "HELP"
       - Eğer karşılaştırma isteniyorsa intent = "COMPARE"
       - Selamlaşma vs ise intent = "CHAT"
       - Parça araması ise intent = "SEARCH"
    5. ÖRNEKLER:
       - "Typical vida var mı?" -> {"intent":"SEARCH","brand":"TYPICAL","part_name":"VİDA","parts":[{"part_name":"VİDA","part_code":null}],"part_code":null,"machine_group":null,"confidence":0.85}
       - "Juki çağanoz ve motor kayışı var mı?" -> {"intent":"SEARCH","brand":"JUKI","parts":[{"part_name":"ÇAĞANOZ","part_code":null},{"part_name":"MOTOR KAYIŞI","part_code":null}],"confidence":0.86}
       - "B2424-354-000 fiyatı ne?" -> {"intent":"PRICE","part_name":"B2424-354-000","part_code":"B2424-354-000","parts":[{"part_name":"B2424-354-000","part_code":"B2424-354-000"}],"confidence":0.90}
       - "Bu parça hangi makinelere uyar?" -> {"intent":"COMPATIBILITY","part_name":"PARÇA","parts":[{"part_name":"PARÇA","part_code":null}],"confidence":0.70}
       - "Selamun aleyküm" -> {"intent":"CHAT","confidence":0.95}
    """
    payload = {
        "contents": [{"parts": [{"text": system_prompt + f"\n\nKULLANICI MESAJI: {text}"}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    text_resp = res["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(text_resp)
                else:
                    return {"intent": "SEARCH", "brand": None, "part_name": text, "machine_group": None}
    except Exception as e:
        logger.error(f"Router Hatası: {e}")
        return {"intent": "SEARCH", "brand": None, "part_name": text, "machine_group": None}

def split_terms(text: str):
    if not text:
        return []
    seps = [" ve ", " & ", ",", ";", "/", " ile "]
    parts = [text]
    for sep in seps:
        parts = [p for chunk in parts for p in chunk.split(sep)]
    return [p.strip() for p in parts if p.strip()]

# =========================================================
# 🧠 ANA CHAT ENDPOINT
# =========================================================
@router.post("/send")
@router.post("/expert-chat")
async def chat_endpoint(
    text: str = Form(None),   
    message: str = Form(None),
    history: str = Form("[]")
):
    try:
        user_query = text if text else message
        if not user_query: 
            return {"answer": "Boş mesaj.", "reply": "Boş mesaj.", "sources": [], "debug_intent": None}

        logger.info(f"📨 [GİRİŞ] Mesaj: {user_query}")

        # 1. ANALİZ ET (Router)
        analysis = await analyze_intent_with_gemini(user_query)
        
        intent = analysis.get("intent", "CHAT")
        extracted_brand = analysis.get("brand")
        extracted_part = analysis.get("part_name")
        extracted_group = analysis.get("machine_group")

        # ✅ parts normalizasyonu
        parts = analysis.get("parts")
        if not parts:
            if extracted_part:
                parts = [{"part_name": extracted_part, "part_code": analysis.get("part_code")}]
            else:
                parts = []

        # ✅ Gemini kaçırırsa fallback split
        if len(parts) <= 1 and intent == "SEARCH":
            fallback_parts = split_terms(user_query)
            if len(fallback_parts) > 1:
                parts = [{"part_name": p, "part_code": None} for p in fallback_parts]

        analysis["parts"] = parts

        # Eğer sohbet ise (Selam vs.) veya parça bulunamadıysa
        if intent == "CHAT" or not extracted_part:
            return {
                "answer": "Aleykümselam ustam. Hangi parçayı arıyorsun? Marka veya parça adı söyle, hemen depoya bakayım.",
                "reply": "Buyur ustam?",
                "sources": [],
                "debug_intent": analysis
            }

        # ✅ Multi-part varsa her parça için ayrı arama yap
        if intent == "SEARCH" and len(parts) > 1:
            all_sources = []
            for part in parts:
                part_name = part.get("part_name")
                if not part_name:
                    continue

                query_vector = get_text_embedding(part_name)
                if not query_vector:
                    continue

                results = await search_vector_db(
                    query_vector, 
                    brand_filter=extracted_brand, 
                    limit=5
                )

                for p in results:
                    p_code = p.get('PartCode', '-')
                    p_name = p.get('PartName', 'Bilinmeyen')
                    p_brand = p.get('MachineBrand', '-')
                    p_model = p.get('MachineModel', '')
                    p_desc = p.get('Description', '')
                    
                    safe_code = urllib.parse.quote(p_code.strip())
                    buy_link = f"{SHOP_BASE_URL}{safe_code}"

                    all_sources.append({
                        "code": p_code,
                        "name": p_name,
                        "brand": p_brand,
                        "buy_url": buy_link,
                        "machine_model": p_model,
                        "description": p_desc,
                        "query": part_name
                    })

            if not all_sources:
                msg = "Ustam, birden fazla parça istedin ama uygun sonuç çıkmadı."
                return {"answer": msg, "reply": msg, "sources": [], "debug_intent": analysis}

            msg = "Birden fazla parça için sonuçları ayrı ayrı listeliyorum ustam."
            return {"answer": msg, "reply": msg, "sources": all_sources, "debug_intent": analysis}

        logger.info(f"🇹🇷 Arama Yapılıyor -> Marka: {extracted_brand} | Parça: {extracted_part}")

        # 2. VEKTÖR OLUŞTUR
        query_vector = get_text_embedding(extracted_part)

        if not query_vector:
            return {
                "answer": "Teknik bir sorun oldu, beyin (embedding) yanıt vermedi.",
                "reply": "Hata",
                "sources": [],
                "debug_intent": analysis
            }

        # 3. VERİTABANINDA ARA
        results = await search_vector_db(
            query_vector, 
            brand_filter=extracted_brand, 
            limit=5
        )
        
        logger.success(f"📦 Sonuç Sayısı: {len(results)}")

        # 4. CEVABI HAZIRLA
        if not results:
            msg = f"Ustam, '{extracted_part}' parçası için veritabanında uygun sonuç bulamadım. Marka ({extracted_brand}) doğru mu? Belki parça ismi farklıdır?"
            return {"answer": msg, "reply": msg, "sources": [], "debug_intent": analysis}

        # Gemini'ye sunulacak metin ve Frontend için kaynak listesi
        context_lines = []
        sources_list = []
        
        for p in results:
            p_code = p.get('PartCode', '-')
            p_name = p.get('PartName', 'Bilinmeyen')
            p_brand = p.get('MachineBrand', '-')
            p_model = p.get('MachineModel', '')
            p_desc = p.get('Description', '')
            
            safe_code = urllib.parse.quote(p_code.strip())
            buy_link = f"{SHOP_BASE_URL}{safe_code}"

            line = f"- Marka: {p_brand} | Model: {p_model} | Parça: {p_name} ({p_code}) | Detay: {p_desc}"
            context_lines.append(line)
            
            sources_list.append({
                "code": p_code,
                "name": p_name,
                "brand": p_brand,
                "buy_url": buy_link,
                "machine_model": p_model,
                "description": p_desc
            })

        context_text = "\n".join(context_lines)

        # 5. FİNAL CEVAP
        final_prompt = f"""
        Sen sanayi yedek parça uzmanısın (Partalog AI).
        
        KULLANICI SORUSU: "{user_query}"
        
        DEPODAN BULDUĞUN PARÇALAR:
        {context_text}
        
        GÖREV:
        1. Kullanıcıya bulduğun parçaları listele.
        2. Marka ve Model uyumuna dikkat çek.
        3. Samimi, kısa ve öz, usta ağzıyla konuş.
        4. Link verme, zaten sistem gösterecek.
        """

        async with aiohttp.ClientSession() as session:
            payload = {"contents": [{"parts": [{"text": final_prompt}]}]}
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    ai_reply = (await resp.json())["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    ai_reply = "Sonuçlar yukarıda listelendi ustam."

        return {
            "answer": ai_reply,
            "reply": ai_reply,
            "sources": sources_list,
            "debug_intent": analysis
        }

    except Exception as e:
        logger.error(f"Chat Hatası: {e}")
        return {
            "answer": "Sistemsel bir hata oluştu ustam.",
            "reply": "Hata",
            "sources": [],
            "debug_intent": None
        }