"""Pipeline de descarga de archivos: Botmaker/CDN → S3 (§6.5).

Estados (mismo CHECK que la tabla): ok / forbidden / not_found / error / skipped.
Nunca debe frenar la etapa por un archivo.
"""

import logging
from dataclasses import dataclass

import requests

from worker.etl.botmaker import BotmakerClient

logger = logging.getLogger("koala.worker.files")


@dataclass
class DownloadResult:
    status: str
    s3_key: str | None = None
    size_bytes: int | None = None
    content_type: str | None = None


def s3_file_key(tenant_id: str, message_id: str, file_type: str, url: str) -> str:
    filename = url.split("/")[-1].split("?")[0] or f"{file_type}_{message_id}"
    return f"tenants/{tenant_id}/files/{message_id}/{file_type}/{filename}"


def download_to_s3(
    client: BotmakerClient,
    s3,
    bucket: str,
    *,
    url: str,
    tenant_id: str,
    message_id: str,
    file_type: str,
) -> DownloadResult:
    if not url:
        return DownloadResult(status="skipped")

    try:
        # 1) intento directo (muchos archivos siguen siendo públicos)
        resp = client.download(url)

        # 2) privada/expirada → temp-link y reintento
        if resp.status_code == 403:
            temp_url = client.get_temp_link(url, expire_minutes=10)
            if not temp_url:
                logger.warning("No se pudo regenerar firma temporal para %s", url)
                return DownloadResult(status="forbidden")
            resp = client.download(temp_url)

        # 3) no existe
        if resp.status_code == 404:
            return DownloadResult(status="not_found")

        # 4) el CDN a veces responde 200 con JSON {"message":"No file found"} (§11.3)
        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "application/json" in ctype:
            preview = (resp.text or "")[:300]
            if "no file found" in preview.lower():
                return DownloadResult(status="not_found")

        resp.raise_for_status()

        # 5) subir a S3 en streaming
        key = s3_file_key(tenant_id, message_id, file_type, url)
        body = resp.raw if hasattr(resp, "raw") and resp.raw is not None else resp.content
        extra = {"ContentType": ctype} if ctype else {}
        if hasattr(body, "read"):
            s3.upload_fileobj(body, bucket, key, ExtraArgs=extra or None)
            size = int(resp.headers.get("Content-Length") or 0) or None
        else:
            s3.put_object(Bucket=bucket, Key=key, Body=body, **extra)
            size = len(body)
        if size is None:
            try:
                size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]
            except Exception:
                size = None

        return DownloadResult(
            status="ok", s3_key=key, size_bytes=size, content_type=ctype or None
        )

    except requests.RequestException as e:
        logger.warning("Recurso inaccesible %s (%s)", url, e)
        return DownloadResult(status="error")
    except Exception as e:
        logger.error("Error descargando %s: %s", url, e)
        return DownloadResult(status="error")
