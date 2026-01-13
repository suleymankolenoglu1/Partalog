"""
Partalog AI Service - Configuration
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


class Settings(BaseSettings):
    # GENEL
    APP_NAME: str = "Partalog AI Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = Field(default=True)
    
    # SUNUCU
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)
    
    # YOLLAR
    BASE_DIR: Path = Path(__file__).parent
    MODELS_DIR: Path = Field(default=Path("models"))
    DATA_DIR: Path = Field(default=Path("data"))
    TEMP_DIR: Path = Field(default=Path("data/temp"))
    VECTOR_DB_DIR: Path = Field(default=Path("data/vector_db"))
    
    # YOLO
    YOLO_MODEL_PATH: str = Field(default="models/best.pt")
    YOLO_CONFIDENCE:  float = Field(default=0.25)
    YOLO_IMG_SIZE: int = Field(default=1280)
    
    # OCR
    OCR_LANGS: list = Field(default=["en"])
    OCR_USE_GPU: bool = Field(default=False)
    
    # CLIP
    CLIP_MODEL_NAME: str = Field(default="ViT-B-32")
    CLIP_PRETRAINED:  str = Field(default="openai")
    
    # SAM / SAM-HQ
    SAM_MODEL_PATH: str = Field(default="models/sam_hq_vit_b.pth")  # SAM-HQ öncelikli
    SAM_MODEL_TYPE: str = Field(default="vit_b")
    SAM_ENABLED: bool = Field(default=True)
    SAM_MIN_AREA: int = Field(default=100)  # Küçük parçalar için düşürüldü
    
    # VECTOR DB
    VECTOR_DB_COLLECTION:  str = Field(default="part_embeddings")
    
    # ARAMA
    SEARCH_DEFAULT_TOP_K: int = Field(default=10)
    SEARCH_DEFAULT_THRESHOLD: float = Field(default=0.5)
    
    class Config:
        env_file = ".env"
        extra = "ignore"
    
    def ensure_directories(self):
        self. MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self. TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.VECTOR_DB_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_directories()