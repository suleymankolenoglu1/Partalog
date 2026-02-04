"""
Chat API - EXPERT MODE V34 (Router + Dictionary Edition)
---------------------------------------------------------
Bu sürüm:
1. YENİ ÖZELLİK (ROUTER): "classify_intent" fonksiyonu eklendi.
   - "Selam", "Deneme", "Test" gibi mesajları veritabanına sokmadan direkt yanıtlar.
   - Sadece "Arama" niyetli mesajlar veritabanına ve sözlüğe gider.
2. SÖZLÜK ZORLAMASI: V33'teki sözlük entegrasyonu aynen korundu.
3. HIZ: Router için de Gemini 2.0 Flash kullanılır (Çok hızlıdır).
"""

import aiohttp
import json
import re
import os
import urllib.parse
from fastapi import APIRouter, Form, File, UploadFile
from loguru import logger
from config import settings
from typing import Optional

# Servis importu (Vektör DB)
try:
    from services.vector_db import search_parts
except ImportError:
    logger.warning("⚠️ Vector DB servisi bulunamadı, Mock servisi devrede.")
    async def search_parts(query: str, strict_filter: str = None, k: int = 5):
        return []

router = APIRouter()

# Gemini 2.0 Flash (Hız ve Maliyet İçin)
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"

# ⚙️ MÜŞTERİ AYARLARI
SHOP_BASE_URL = "https://www.parcagalerisi.com/ara/"

# =========================================================
# 📚 SÖZLÜK YÖNETİMİ (DICTIONARY LAYER)
# =========================================================
DICTIONARY_PATHS = [
    "sanayi_sozlugu.json", 
    "/Users/suleymankolenoglu/Desktop/Projeler/Katalogcu/partalog-ai/sanayi_sozlugu.json" 
]

SANAYI_SOZLUGU = {}  
TERIM_HARITASI = {}  

def load_dictionary():
    global SANAYI_SOZLUGU, TERIM_HARITASI
    found_path = None
    try:
        for path in DICTIONARY_PATHS:
            if os.path.exists(path):
                found_path = path
                break
        
        if found_path:
            with open(found_path, "r", encoding="utf-8") as f:
                SANAYI_SOZLUGU = json.load(f)
            
            for eng_key, tr_list in SANAYI_SOZLUGU.items():
                for tr_word in tr_list:
                    key = tr_word.lower().strip()
                    TERIM_HARITASI[key] = eng_key
            logger.success(f"📚 Sanayi Sözlüğü Yüklendi: {found_path} ({len(SANAYI_SOZLUGU)} terim)")
        else:
            logger.warning(f"⚠️ Sözlük dosyası bulunamadı! Aranan yollar: {DICTIONARY_PATHS}")
            SANAYI_SOZLUGU = {}
    except Exception as e:
        logger.error(f"⚠️ Sözlük yükleme hatası: {e}")

load_dictionary()

# ---------------------------------------------------------
# 🧹 YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
def extract_pure_name(name: str) -> str:
    if not name: return ""
    clean = name.upper()
    clean = re.sub(r'_\d+$', '', clean) 
    clean = re.sub(r'\([^)]*\)', '', clean)
    clean = re.sub(r'\d+', '', clean)
    suffixes = [" ASM", " COMP", " SET", " ASSY", "/", "-"]
    for s in suffixes: clean = clean.replace(s, " ")
    clean = " ".join(clean.split()) 
    return clean

def extract_code_from_text(text: str) -> Optional[str]:
    match = re.search(r'\b([A-Za-z0-9-]{3,})\b', text)
    if match:
        candidate = match.group(1)
        if any(char.isdigit() for char in candidate) or "-" in candidate:
            return candidate
    return None

# =========================================================
# 🚦 [YENİ] INTENT CLASSIFIER (NİYET OKUYUCU)
# =========================================================
async def classify_intent(text: str) -> dict:
    """
    Kullanıcının niyetini (Arama mı? Sohbet mi?) analiz eder.
    Dönüş Formatı (JSON): { "intent": "SEARCH" | "CHAT", "reply": "...", "query": "..." }
    """
    logger.info(f"🚦 [ROUTER] Niyet Analizi: '{text}'")
    
    system_prompt = """
    Sen Partalog AI Asistanının beynisin. Görevin gelen mesajı sınıflandırmak.
    Çıktı SADECE geçerli bir JSON olmalı. Markdown (```json) kullanma.

    1. DURUM: Eğer kullanıcı bir YEDEK PARÇA arıyorsa (fiyat, stok, kod, parça adı vb.):
       - "intent": "SEARCH"
       - "query": "Kullanıcının aradığı parçanın en sade hali (temizlenmiş)"

    2. DURUM: Eğer kullanıcı SOHBET ediyor, SELAM veriyor, TEST yapıyor veya alakasız bir şey yazıyorsa:
       - "intent": "CHAT"
       - "reply": "Kullanıcıya verilecek nazik, kısa ve profesyonel cevap."
    
    ÖRNEKLER:
    - "Lüper fiyatı ne?" -> {"intent": "SEARCH", "query": "Lüper"}
    - "B-1234 var mı?" -> {"intent": "SEARCH", "query": "B-1234"}
    - "Selamun aleyküm" -> {"intent": "CHAT", "reply": "Aleyküm selam! Size yedek parça konusunda nasıl yardımcı olabilirim?"}
    - "Deneme" -> {"intent": "CHAT", "reply": "Sistemimiz aktif ve sorunsuz çalışıyor. Hangi parçayı arıyorsunuz?"}
    - "Nasılsın" -> {"intent": "CHAT", "reply": "Teşekkürler, ben bir yapay zekayım ve parça bulmak için hazırım. Siz nasılsınız?"}
    """

    payload = {
        "contents": [{ "parts": [{"text": system_prompt + f"\n\nMESAJ: {text}"}] }],
        "generationConfig": {"response_mime_type": "application/json"} # JSON zorlaması
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    json_str = res["candidates"][0]["content"]["parts"][0]["text"]
                    result = json.loads(json_str)
                    logger.info(f"   ↳ 🚦 Karar: {result['intent']}")
                    return result
    except Exception as e:
        logger.error(f"Router Hatası: {e}")
        # Hata olursa güvenli mod: Arama yapmaya çalışsın
        return {"intent": "SEARCH", "query": text}

# ---------------------------------------------------------
# ÇEVİRİ FONKSİYONU (V33 Aynen Korundu)
# ---------------------------------------------------------
async def translate_to_technical_english(text: str) -> str:
    logger.info(f"🔄 [ÇEVİRİ] Başlıyor: '{text}'")
    clean_text = text.lower().strip()
    
    extracted_code = extract_code_from_text(text)
    if extracted_code:
        return extracted_code

    if clean_text in TERIM_HARITASI: 
        return TERIM_HARITASI[clean_text]

    dictionary_context = json.dumps(SANAYI_SOZLUGU, ensure_ascii=False)
    system_prompt = f"""
    GÖREV: Kullanıcının tarif ettiği parçanın İNGİLİZCE TEKNİK ADINI bul.
    Sözlük dışı ise türk sanayisinde nasıl kullanılır onu bul. kelimeyi yaz.
    MEVCUT SÖZLÜK: {dictionary_context}
    """
    
    payload = {"contents": [{ "parts": [{"text": system_prompt + f"\n\nKULLANICI TARİFİ: {text}"}] }]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    return res["candidates"][0]["content"]["parts"][0]["text"].strip().replace('"', '').upper()
    except Exception:
        pass
    
    return text

# =========================================================
# 🚀 ANA CHAT FONKSİYONU (/ask)
# =========================================================
@router.post("/ask")
@router.post("/expert-chat")
async def expert_chat(
    text: str = Form(...),
    history: str = Form("[]"),
    file: Optional[UploadFile] = File(None) 
):
    try:
        logger.info("\n" + "="*60)
        logger.info(f"📨 [GİRİŞ] Mesaj: {text}")

        # -------------------------------------------------
        # ADIM 1: NİYET ANALİZİ (ROUTER) 🚦
        # -------------------------------------------------
        intent_result = await classify_intent(text)

        # EĞER SOHBET İSE -> DİREKT CEVAP DÖN (DB'YE GİTME)
        if intent_result.get("intent") == "CHAT":
            logger.success(f"🗣️ [SOHBET MODU] Direkt cevap veriliyor.")
            return {
                "answer": intent_result.get("reply", "Merhaba, size nasıl yardımcı olabilirim?"),
                "sources": [],
                "debug_intent": {"mode": "chat", "status": "direct_reply"}
            }

        # EĞER ARAMA İSE -> DEVAM ET (query güncellendi)
        search_text = intent_result.get("query", text)
        logger.info(f"🔎 [ARAMA MODU] Sorgu: {search_text}")

        # -------------------------------------------------
        # ADIM 2: ÇEVİRİ VE HAZIRLIK
        # -------------------------------------------------
        search_query = await translate_to_technical_english(search_text)
        extracted_code = extract_code_from_text(search_text)
        is_code_search = bool(extracted_code)
        
        # -------------------------------------------------
        # ADIM 3: VEKTÖR ARAMA
        # -------------------------------------------------
        raw_parts = []
        search_status = "normal"
        
        if is_code_search:
            # Önce kodu tam eşleşme olarak ara
            raw_parts = await search_parts(search_query, strict_filter=extracted_code, k=50)
            if raw_parts:
                search_status = "exact_match"
            else:
                raw_parts = await search_parts(search_query, k=50)
                if raw_parts: search_status = "similar_suggestion"
        else:
            raw_parts = await search_parts(search_query, k=50)
        
        # -------------------------------------------------
        # ADIM 4: VERİ İŞLEME & SMART MERGE
        # -------------------------------------------------
        unique_parts_map = {}
        target_clean = search_query.lower().replace("_", " ").strip()

        for p in raw_parts:
            code = str(p.get('part_code') or p.get('code') or "").strip()
            if len(code) < 3: continue
            
            name = str(p.get('part_name') or p.get('name') or "").strip()
            desc = str(p.get('description') or "").strip()
            
            is_unknown = any(x in name.lower() for x in ["unknown", "belirtilmemiş"]) or (not name)
            if (not name or is_unknown) and desc: name = desc; is_unknown = False 

            part_obj = {"code": code, "name": name, "desc": desc, "model": p.get('model'), "is_unknown": is_unknown, "score": p.get('similarity', 0)}

            if code not in unique_parts_map:
                unique_parts_map[code] = part_obj
            else:
                existing = unique_parts_map[code]
                if existing["is_unknown"] and not is_unknown:
                    unique_parts_map[code] = part_obj

        # -------------------------------------------------
        # ADIM 5: SIRALAMA VE AI CONTEXT HAZIRLIĞI
        # -------------------------------------------------
        def calc_prio(part):
            clean_name = part["name"].lower().replace("_", " ").strip()
            if clean_name == target_clean: return 0 
            if clean_name.startswith(target_clean): return 1
            if target_clean in clean_name: return 2
            return 3

        merged_parts = sorted(
            list(unique_parts_map.values()), 
            key=lambda x: (x["is_unknown"], calc_prio(x), len(x["name"]), -x["score"])
        )[:5]

        ai_data_points = []
        if merged_parts:
            for p in merged_parts:
                safe_code = urllib.parse.quote(p["code"].strip())
                p["buy_url"] = f"{SHOP_BASE_URL}{safe_code}"
                p["is_available"] = True
                pure_name = extract_pure_name(p['name'])
                data_point = f"Code: {p['code']} | RAW Name: {p['name']} | PURE Function: {pure_name}"
                ai_data_points.append(data_point)

        # -------------------------------------------------
        # ADIM 6: SATIŞ DANIŞMANI CEVABI (SÖZLÜK DESTEKLİ)
        # -------------------------------------------------
        context_str = "\n".join(ai_data_points) if ai_data_points else "Bulunamadı."
        dictionary_context = json.dumps(SANAYI_SOZLUGU, ensure_ascii=False)
        
        intro = "Listede en üstteki parçayı analiz et."
        if search_status == "similar_suggestion": intro = f"Aranan {extracted_code} yok. Benzerleri listele."
        elif search_status == "exact_match": intro = f"Tam eşleşme: {extracted_code}."

        system_prompt = f"""
        Rol: Kıdemli Endüstriyel Analist ve Satış Danışmanı (Partalog AI).
        
        DURUM: {intro}
        VERİLER: 
        {context_str}
        
        REFERANS SÖZLÜK:
        {dictionary_context}
        
        GÖREVİN: Kullanıcıya doğal, akıcı bir dille cevap vermek.
        
        KURALLAR:
        1. **SANAYİ AĞZI KULLAN:** RAW Name İngilizce ise, 'REFERANS SÖZLÜK'teki Türkçe karşılığını kullan.
           - Örn: "THROAT PLATE" -> "İğne Plakası".
        
        2. **AKICI KONUŞ:** Madde işareti kullanma, sohbet eder gibi yaz.
        
        3. **SONUÇ:** Fiyat için yönlendir.
        """
        
        gemini_parts = [{"text": system_prompt + f"\n\nKULLANICI SORUSU: {text}"}]
        
        if file: pass 

        payload = {"contents": [{ "parts": gemini_parts }]}
        
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res_json = await resp.json()
                    final_answer = res_json["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    final_answer = "Sistem şu an cevap veremiyor."

        return {
            "answer": final_answer, 
            "sources": merged_parts, 
            "debug_intent": {"mode": "v34_router", "status": search_status}
        }

    except Exception as e:
        logger.error(f"🔥 KRİTİK HATA: {e}")
        return {"answer": "Bir hata oluştu. Lütfen tekrar deneyin.", "sources": []}