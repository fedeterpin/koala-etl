"""Acceso a S3/MinIO. Media servida SOLO con URLs prefirmadas de TTL corto (§8.3)."""

from functools import lru_cache

import boto3
from botocore.config import Config

from app.core.config import get_settings


@lru_cache
def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key or None,
        aws_secret_access_key=settings.s3_secret_key or None,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4"),
    )


def file_key(tenant_id: str, message_id: str, file_type: str, filename: str) -> str:
    return f"tenants/{tenant_id}/files/{message_id}/{file_type}/{filename}"


def backup_key(tenant_id: str, backup_job_id: int) -> str:
    return f"tenants/{tenant_id}/backups/{backup_job_id}.zip"


def presign_get(s3_key: str, *, ttl: int | None = None, filename: str | None = None) -> str:
    settings = get_settings()
    params = {"Bucket": settings.s3_bucket, "Key": s3_key}
    if filename:
        params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=min(ttl or settings.presign_ttl_seconds, 300),  # techo duro de 5 min
    )
