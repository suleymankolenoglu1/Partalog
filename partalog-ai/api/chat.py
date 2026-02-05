"""
Partalog AI - Chat API (Expert Mode V39 - Compatibility Fix)
------------------------------------------------
1. COMPATIBILITY: C# için hem 'answer' hem 'reply' hem de 'sources' döner.
2. LOGIC: V38'in zekası (Router + Regex + Sözlük + Sayaçlar) aynen korundu.
"""

import aiohttp
import json
import os
import re
import urllib.parse
from fastapi import APIRouter, Form
from loguru import logger
from config import settings
from services.vector_db import search_parts

router = APIRouter()

# ⚡️ Gemini 2.0 Flash
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"
SHOP_BASE_URL = "https://www.parcagalerisi.com/ara/"

# =========================================================
# 🛠️ TÜRKÇE NORMALİZASYON
# =========================================================
def tr_upper(text: str) -> str:
    if not text: return ""
    text = text.replace("i", "İ").replace("ı", "I")
    text = text.replace("ğ", "Ğ").replace("ü", "Ü").replace("ş", "Ş").replace("ö", "Ö").replace("ç", "Ç")
    return text.upper()

# =========================================================
# 📚 SÖZLÜK YÖNETİMİ
# =========================================================
INDUSTRIAL_DICT = {}

def load_dictionary():
    global INDUSTRIAL_DICT
    file_path = "sanayi_sozlugu.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                INDUSTRIAL_DICT = json.load(f)
            logger.success(f"📚 Sanayi Sözlüğü Yüklendi: {len(INDUSTRIAL_DICT)} terim.")
        except Exception as e:
            logger.error(f"⚠️ Sözlük hatası: {e}")
            INDUSTRIAL_DICT = {}
    else:
        logger.warning("⚠️ Sözlük dosyası yok.")

load_dictionary()

def search_in_dictionary(query):
    query_clean = tr_upper(query.strip())
    logger.debug(f"📖 Sözlükte aranıyor: '{query_clean}'")
    for eng_term, tr_list in INDUSTRIAL_DICT.items():
        for tr_word in tr_list:
            if tr_upper(tr_word) in query_clean:
                logger.success(f"✅ Sözlük Eşleşmesi: '{tr_word}' -> '{eng_term}'")
                return eng_term
    return None

# =========================================================
# 🛠️ YARDIMCI ARAÇLAR
# =========================================================
def extract_code_from_text(text: str):
    match = re.search(r'\b([A-Za-z0-9-]{3,})\b', text)
    if match:
        candidate = match.group(1)
        if any(char.isdigit() for char in candidate) or "-" in candidate:
            return candidate
    return None

# =========================================================
# 🚦 INTENT CLASSIFIER
# =========================================================
async def classify_intent(text: str) -> dict:
    system_prompt = """
    Sen bir Router'sın. JSON dön.
    1. DURUM: Parça arıyorsa "intent": "SEARCH". 
       "query" alanına 'var mı', 'fiyat', 'lazım', 'arıyorum' gibi sohbet eklerini at.
       ANCAK: Parçayı niteleyen sıfatları (Ara, Alt, Üst, Ön, Arka, Hareketli, Sabit, Sağ, Sol) ASLA SİLME.
       Örn: "Ara kablo var mı" -> "query": "Ara kablo" (Doğru)
       Örn: "Kablo var mı" -> "query": "Kablo"
       Örn: "Alt bıçak fiyatı" -> "query": "Alt bıçak"
       
    2. DURUM: Sohbet ise "intent": "CHAT", "reply": "Parça aramaya hazırım".
    """
    payload = {
        "contents": [{"parts": [{"text": system_prompt + f"\n\nMESAJ: {text}"}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    return json.loads(res["candidates"][0]["content"]["parts"][0]["text"])
    except:
        return {"intent": "SEARCH", "query": text}

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
        if not user_query: return {"answer": "Boş mesaj gönderilemez ustam.", "reply": "Boş mesaj.", "sources": []}

        logger.info(f"📨 [GİRİŞ] Mesaj: {user_query}")

        # 1. NİYET ANALİZİ
        intent_result = await classify_intent(user_query)
        if intent_result.get("intent") == "CHAT":
            reply_text = intent_result.get("reply", "Buyur ustam?")
            return {"answer": reply_text, "reply": reply_text, "sources": []}

        search_text = intent_result.get("query", user_query)
        logger.info(f"🔎 Router: '{user_query}' -> '{search_text}'")
        
        # 2. HAZIRLIK
        extracted_code = extract_code_from_text(search_text)
        english_term = search_in_dictionary(search_text) 
        
        # 3. FALLBACK
        if not english_term and not extracted_code:
            logger.info("🤷‍♂️ Sözlükte yok, Gemini'ye soruluyor...")
            prompt = f"Identify technical English name for sewing part: '{search_text}'. Return ONLY term."
            async with aiohttp.ClientSession() as session:
                payload = {"contents": [{"parts": [{"text": prompt}]}]}
                async with session.post(GEMINI_API_URL, json=payload) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        english_term = res["candidates"][0]["content"]["parts"][0]["text"].strip()
        
        # 4. ARAMA YAP
        db_results = []
        if extracted_code:
            logger.info(f"🎯 Kod ile aranıyor: {extracted_code}")
            res = await search_parts(search_text, strict_filter=extracted_code, k=5)
            logger.info(f"   ↳ Kod: {len(res)}")
            db_results.extend(res)

        if english_term:
            logger.info(f"🌍 Çeviri ile aranıyor: {english_term}")
            res = await search_parts(english_term, k=5)
            logger.info(f"   ↳ Çeviri: {len(res)}")
            db_results.extend(res)
        
        res = await search_parts(search_text, k=3)
        logger.info(f"   ↳ Türkçe: {len(res)}")
        db_results.extend(res)

        # Tekilleştirme
        unique_parts = {res['code']: res for res in db_results}.values()
        logger.success(f"📦 TOPLAM TEKİL SONUÇ: {len(unique_parts)}")

        # 5. CEVAP OLUŞTUR
        # Frontend için source listesi hazırlayalım (C# tarafında kullanılıyorsa)
        sources_list = []
        context_lines = []
        
        if unique_parts:
            for p in unique_parts:
                safe_code = urllib.parse.quote(p['code'].strip())
                buy_link = f"{SHOP_BASE_URL}{safe_code}"
                
                # AI Context için metin
                line = f"- Kod: {p['code']} | Ad: {p['name']} | Sayfa: {p.get('page','?')} | Link: {buy_link}"
                context_lines.append(line)
                
                # C# (Frontend) için obje
                sources_list.append({
                    "code": p['code'],
                    "name": p['name'],
                    "description": p.get('desc', ''),
                    "page": p.get('page', ''),
                    "buy_url": buy_link
                })
            context_text = "\n".join(context_lines)
        else:
            context_text = "Veritabanında bulunamadı."

        system_prompt = f"""
        Sen Partalog AI, Sanayi Yedek Parça Uzmanısın.
        SORU: "{user_query}"
        BULUNAN PARÇALAR:
        {context_text}
        
        GÖREVİN:
        1. En uygun parçayı öner. Kodunu, İsmini ve Sayfa Numarasını söyle.
        2. Satın alma linki verebileceğini ima et.
        3. Samimi bir usta dili kullan.
        4. Parça yoksa dürüstçe "Katalogda yok" de.
        """

        payload = {"contents": [{"parts": [{"text": system_prompt}]}]}
        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as resp:
                if resp.status == 200:
                    res = await resp.json()
                    final_reply = res["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    final_reply = "Aradığın parçaları buldum. Bunları mı arıyordun?."

        # 👇 KRİTİK NOKTA: HERKESİN GÖNLÜNÜ ALAN FORMAT
        return {
            "answer": final_reply,  # Eski C# kodu bunu bekliyor olabilir
            "reply": final_reply,   # Yeni standart
            "sources": sources_list # Frontend kart göstermek isterse
        }

    except Exception as e:
        logger.error(f"🔥 Chat Hatası: {e}")
        return {"answer": "Teknik bir hata oluştu ustam.", "reply": "Hata", "sources": []}