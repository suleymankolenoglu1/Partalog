from config import settings
from services.storage.local_storage import save_bytes as local_save
from services.storage.s3_storage import save_bytes as s3_save

def save_file(file_bytes: bytes, object_key: str) -> str:
    if settings.STORAGE_PROVIDER == "s3":
        return s3_save(file_bytes, object_key)
    return local_save(file_bytes, object_key)