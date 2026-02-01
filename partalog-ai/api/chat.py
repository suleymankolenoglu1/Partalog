"""
Chat API - Gemini 2.0 Flash Lite (Partalog AI v1.2 - Self Learning & Detective Mode)
Bu modül, kullanıcı sorgularını analiz eder ve 'sanayi_sozlugu.json' dosyasından
öğrendiği dinamik terminolojiyi kullanır.
"""

import aiohttp
import json
import base64
import io
import os
from PIL import Image
from fastapi import APIRouter, Form, File, UploadFile, HTTPException
from loguru import logger
from config import settings
from typing import Optional

router = APIRouter()

# ⚡ MODEL: gemini-2.0-flash-lite
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent?key={settings.GEMINI_API_KEY}"

# ==========================================
# 🧠 DİNAMİK HAFIZA YÜKLEYİCİ
# ==========================================
def load_dynamic_terminology():
    """
    'train_dictionary.py' tarafından oluşturulan JSON sözlüğünü okur
    ve Prompt formatına çevirir.
    """
    json_path = "sanayi_sozlugu.json" # Ana dizinde olduğu varsayılır
    
    # Eğer dosya henüz oluşmadıysa (ilk kurulum), bu varsayılan listeyi kullan:
    default_mapping = """
    - İğne -> "NEEDLE"
    - Vida -> "SCREW"
    - Lüper -> "LOOPER"
    - Plaka, Ayna -> "THROAT PLATE"
    - Dişli -> "FEED DOG"
    - Alyan -> "HEX SOCKET SCREW"
    """

    if not os.path.exists(json_path):
        return f"TERMS MAPPING (DEFAULT):\n{default_mapping}"

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # JSON'ı LLM'in anlayacağı liste formatına çeviriyoruz
        # Örn: { "SCREW": ["Vida", "Civata"] } -> - Vida, Civata -> "SCREW"
        mapping_text = "TERMS MAPPING (DYNAMICALLY LEARNED FROM DB):\n"
        
        for eng_term, tr_list in data.items():
            if tr_list:
                tr_str = ", ".join(tr_list)
                mapping_text += f"- {tr_str} -> \"{eng_term}\"\n"
        
        return mapping_text
    except Exception as e:
        logger.error(f"Sözlük yükleme hatası: {e}")
        return f"TERMS MAPPING (FALLBACK):\n{default_mapping}"

# 🔥 SİSTEM AYAĞA KALKARKEN SÖZLÜĞÜ YÜKLE
TERMINOLOGY_HINT = load_dynamic_terminology()

@router.post("/expert-chat")
async def expert_chat(
    text: str = Form(...),
    history: str = Form("[]"), # ✨ Sohbet Geçmişi
    file: Optional[UploadFile] = File(None) 
):
    try:
        parts = []
        
        # 1. Geçmişi ve Yeni Mesajı Hazırla
        try:
            chat_history = json.loads(history)
            # Sadece son 3 mesajı al ki hafıza çok kirlenmesin
            history_text = "\n".join([f"{msg['role'].upper()}: {msg['text']}" for msg in chat_history[-3:]])
        except:
            history_text = "NO HISTORY"

        # Prompt'a hem geçmişi hem şimdiki soruyu veriyoruz
        parts.append({"text": f"CHAT HISTORY (Context Only):\n{history_text}\n\nCURRENT USER QUERY (Focus Here): {text}"})

        # 2. Resim Varsa İşle
        if file:
            try:
                content = await file.read()
                image = Image.open(io.BytesIO(content)).convert("RGB")
                image.thumbnail((1024, 1024)) 
                buffered = io.BytesIO()
                image.save(buffered, format="JPEG", quality=85)
                base64_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                parts.append({
                    "inline_data": {
                        "mime_type": "image/jpeg", 
                        "data": base64_image
                    }
                })
                parts.append({"text": "Image uploaded. Prioritize visual identification over text history."})
            except Exception as img_err:
                logger.error(f"Resim hatası: {img_err}")

        # 3. Sistem Promptu (V1.2 - SELF LEARNING & DETECTIVE MODE 🕵️‍♂️)
        # Not: TERMINOLOGY_HINT artık dinamik olarak doluyor.
        system_prompt = f"""
        ROLE: You are Partalog AI, an elite spare parts expert algorithm.
        
        {TERMINOLOGY_HINT}

        OBJECTIVE:
        Analyze the user query to extract the CORE PART NAME and any SPECIFIC ATTRIBUTES (Size, Model, Type).

        CRITICAL LOGIC & RULES:
        1. **PRIORITIZE CURRENT QUERY:** Ignore history if the topic changes.
        2. **NORMALIZE DIMENSIONS:**
           - If user says "3mm alyan/vida", convert it to `strict_filter: "M3"`.
           - If user says "4mm", convert to `strict_filter: "M4"`.
        3. **IDENTIFY CORE PART:** Use the MAPPING list above to translate Turkish jargon to English Technical names.
        4. **EXTRACT ATTRIBUTES:** Look for short codes like "M4", "B56", "H11". These are `strict_filter`s.
        5. **HANDLE NEGATION:** If user says "NOT B56" (B56 olmayan), put "B56" into `negative_filter`.

        OUTPUT JSON FORMAT:
        {{
            "search_term": "SCREW",       // The main technical English name
            "alternatives": ["BOLT"],     // Synonyms
            "strict_filter": "M4",        // Specific attribute found in text (keep short, e.g., "M4", "B56", "3.0")
            "negative_filter": null,      // If user says "Not X", put "X" here.
            "is_assembly": false,
            "reply_suggestion": "Searching for M4 SCREWS..."
        }}
        """

        payload = {
            "contents": [{ "parts": [{"text": system_prompt}] + parts }],
            "generationConfig": { "response_mime_type": "application/json" }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(GEMINI_API_URL, json=payload) as response:
                if response.status != 200:
                    return {"search_term": "", "reply_suggestion": "Bağlantı hatası."}

                result = await response.json()
                if "candidates" not in result or not result["candidates"]:
                     return {"search_term": "", "reply_suggestion": "Anlaşılamadı."}

                raw_text = result["candidates"][0]["content"]["parts"][0]["text"]
                clean_text = raw_text.replace("```json", "").replace("```", "").strip()
                
                # JSON Parse İşlemi
                try:
                    data = json.loads(clean_text)
                    if isinstance(data, list):
                        return data[0] if len(data) > 0 else {}
                    return data
                except:
                    return {"search_term": "", "reply_suggestion": "Hata oluştu."}

    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return {"search_term": "", "reply_suggestion": "Sistem hatası."}