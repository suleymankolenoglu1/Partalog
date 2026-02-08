import os
from config import settings

def save_bytes(file_bytes: bytes, object_key: str) -> str:
    base_dir = settings.STORAGE_LOCAL_DIR
    os.makedirs(base_dir, exist_ok=True)

    file_path = os.path.join(base_dir, object_key)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "wb") as f:
        f.write(file_bytes)

    return f"/{file_path.replace(os.sep, '/')}"