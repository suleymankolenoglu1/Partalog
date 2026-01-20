# test_models.py
import os
import requests
from dotenv import load_dotenv

load_dotenv()
KEY = os.getenv("GOOGLE_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={KEY}"
response = requests.get(url)

if response.status_code == 200:
    models = response.json().get('models', [])
    print("=== KULLANILABİLİR MODELLER ===")
    for m in models:
        if "gemini" in m['name']:
            print(m['name']) # Örn: models/gemini-1.5-flash-001
else:
    print("Hata:", response.text)