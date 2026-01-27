"""
Partalog AI Service - Configuration (Final)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

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
    
    # --- GEMINI AI (YENİ EKLENDİ) ---
    # Kod içinde 'settings.GEMINI_API_KEY' diyeceğiz,
    # ama bu gidip .env dosyasındaki 'GOOGLE_API_KEY' değerini okuyacak.
    GEMINI_API_KEY: str = Field(default="", validation_alias="GOOGLE_API_KEY")
    
    # YOLO
    YOLO_MODEL_PATH: str = Field(default="models/best.pt")
    YOLO_CONFIDENCE: float = Field(default=0.25)
    YOLO_IMG_SIZE: int = Field(default=1280)
    
    # OCR (EasyOCR - Hotspot için)
    OCR_USE_GPU: bool = Field(default=False)
    
    # PADDLEOCR (Eski Tablo okuma - Yedek olarak dursun)
    PADDLE_USE_GPU: bool = Field(default=False)
    PADDLE_LANG: str = Field(default="en")
    PADDLE_TABLE_MAX_LEN: int = Field(default=800)
    PADDLE_SHOW_LOG: bool = Field(default=False)
    
    # Config Ayarları
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore" # Bilinmeyen değişkenleri hata vermeden geç
    )
    
    def ensure_directories(self):
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()