import boto3
from config import settings

def save_bytes(file_bytes: bytes, object_key: str) -> str:
    client = boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_S3_ENDPOINT,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    )

    client.put_object(
        Bucket=settings.STORAGE_BUCKET,
        Key=object_key,
        Body=file_bytes,
        ContentType="image/png"  # ✅ PNG için düzeltildi
    )

    return f"{settings.STORAGE_BASE_URL}/{object_key}"