"""
Partalog AI Service - Configuration (Final v2.1)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

def _clean_env(value: str) -> str:
    return value.strip().strip('"').strip("'").strip()

class Settings(BaseSettings):
    # GENEL
    APP_NAME: str = "Partalog AI Service"
    APP_VERSION: str = "2.1.0"
    DEBUG: bool = Field(default=True)
    
    # SUNUCU
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    
    # YOLLAR
    BASE_DIR: Path = Path(__file__).parent
    MODELS_DIR: Path = Field(default=Path("models"))
    
    # --- GEMINI AI ---
    # Hem 'GEMINI_API_KEY' hem de 'GOOGLE_API_KEY' olarak gelsen kabul etsin.
    # .env dosyasında hangisi varsa onu alır.
    GEMINI_API_KEY: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    GEMINI_VISUAL_MODEL: str = Field(default="gemini-3-pro-preview")

    # --- VERİTABANI (YENİ EKLENDİ) ---
    # train_dictionary.py artık şifreyi buradan okuyacak.
    # Varsayılan değer boş, .env dosyasından gelmeli.
    DB_CONNECTION_STRING: str = Field(default="")

    # YOLO
    YOLO_MODEL_PATH: str = Field(default="models/best.pt")
    YOLO_CONFIDENCE: float = Field(default=0.25)
    YOLO_IMG_SIZE: int = Field(default=1280)
    
    # OCR (EasyOCR - Hotspot için)
    OCR_USE_GPU: bool = Field(default=False)
    
    # PADDLEOCR (Yedek)
    PADDLE_USE_GPU: bool = Field(default=False)
    PADDLE_LANG: str = Field(default="en")
    PADDLE_TABLE_MAX_LEN: int = Field(default=800)
    PADDLE_SHOW_LOG: bool = Field(default=False)

    # ==========================================
    # 🗂️ STORAGE AYARLARI (LOCAL / S3 COMPAT)
    # ==========================================
    STORAGE_PROVIDER: str = Field(default="local")  # local | s3
    STORAGE_BUCKET: str = Field(default="partalog-visuals")
    STORAGE_BASE_URL: str = Field(default="https://storage.googleapis.com/partalog-visuals")
    STORAGE_LOCAL_DIR: str = Field(default="static/visual-parts")

    # S3 / GCS Interoperability
    STORAGE_S3_ENDPOINT: str = Field(default="https://storage.googleapis.com")
    STORAGE_ACCESS_KEY: str = Field(default="")
    STORAGE_SECRET_KEY: str = Field(default="")
    STORAGE_REGION: str = Field(default="auto")

    # Config Ayarları
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Bilinmeyen değişkenleri hata vermeden geç
    )

    def ensure_directories(self):
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 🔒 TIRNAK TEMİZLEME
    def clean_env_values(self):
        # API ve model
        if self.GEMINI_API_KEY:
            self.GEMINI_API_KEY = _clean_env(self.GEMINI_API_KEY)
        if self.GEMINI_VISUAL_MODEL:
            self.GEMINI_VISUAL_MODEL = _clean_env(self.GEMINI_VISUAL_MODEL)

        # DB
        if self.DB_CONNECTION_STRING:
            self.DB_CONNECTION_STRING = _clean_env(self.DB_CONNECTION_STRING)

        # Storage
        if self.STORAGE_PROVIDER:
            self.STORAGE_PROVIDER = _clean_env(self.STORAGE_PROVIDER)
        if self.STORAGE_BUCKET:
            self.STORAGE_BUCKET = _clean_env(self.STORAGE_BUCKET)
        if self.STORAGE_BASE_URL:
            self.STORAGE_BASE_URL = _clean_env(self.STORAGE_BASE_URL)
        if self.STORAGE_LOCAL_DIR:
            self.STORAGE_LOCAL_DIR = _clean_env(self.STORAGE_LOCAL_DIR)
        if self.STORAGE_S3_ENDPOINT:
            self.STORAGE_S3_ENDPOINT = _clean_env(self.STORAGE_S3_ENDPOINT)
        if self.STORAGE_ACCESS_KEY:
            self.STORAGE_ACCESS_KEY = _clean_env(self.STORAGE_ACCESS_KEY)
        if self.STORAGE_SECRET_KEY:
            self.STORAGE_SECRET_KEY = _clean_env(self.STORAGE_SECRET_KEY)
        if self.STORAGE_REGION:
            self.STORAGE_REGION = _clean_env(self.STORAGE_REGION)


settings = Settings()
settings.ensure_directories()
settings.clean_env_values()