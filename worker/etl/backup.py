"""Generación de paquetes de backup/exportación (§7.4).

ZIP con:
  data/<tabla>.csv         — solo filas del tenant
  files/{message_id}/{file_type}/{filename}
  manifest.json            — fecha, conteos por tabla, versión de esquema, tipo
  README.md                — instrucciones de restauración

Incremental: solo mensajes/archivos nuevos desde el último backup `done`.
"""

import csv
import io
import json
import logging
import os
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    Agent,
    AgentMetric,
    AgentPerformance,
    AgentPerformanceQueue,
    BackupJob,
    Chat,
    ChatDetail,
    ChatTag,
    ChatVariable,
    EncryptionParams,
    Message,
    MessageButton,
    MessageCall,
    MessageCarouselItem,
    MessageContent,
    MessageFile,
    MessageLocation,
    MessageMedia,
    Queue,
    Tenant,
)
from app.services.s3 import backup_key

logger = logging.getLogger("koala.worker.backup")

BACKUP_TTL_DAYS = 7

# Tablas exportadas (las de datos del tenant; no usuarios ni operación interna)
EXPORT_MODELS = [
    Tenant, Agent, Queue, AgentPerformanceQueue, AgentPerformance, AgentMetric,
    Chat, ChatDetail, ChatVariable, ChatTag,
    Message, MessageContent, MessageButton, MessageCarouselItem, MessageMedia,
    MessageLocation, MessageCall, EncryptionParams, MessageFile,
]

# Filtro incremental por tabla: columna de fecha que define "nuevo desde"
INCREMENTAL_DATE_COLUMNS = {
    "messages": "creation_time",
    "message_files": "downloaded_at",
    "agent_metrics": "session_creation_time",
}

README = """# Backup Koala — restauración

Este paquete contiene la copia completa de los datos de su compañía.

## Contenido
- `data/*.csv` — un CSV por tabla (UTF-8, separado por comas, con encabezado).
  Fechas en UTC (ISO 8601).
- `files/<message_id>/<file_type>/<archivo>` — archivos de medios (imágenes,
  audios, documentos) tal como fueron archivados.
- `manifest.json` — fecha de generación, tipo (full/incremental), conteos por
  tabla y versión del esquema.

## Restauración en PostgreSQL
1. Crear el esquema (DDL disponible a pedido o vía Alembic del producto).
2. Importar cada CSV: `\\copy <tabla> FROM 'data/<tabla>.csv' CSV HEADER`.
   Respetar el orden del manifest (respeta claves foráneas).
3. Los archivos de `files/` pueden copiarse a cualquier almacenamiento; la
   columna `message_files.s3_key` indica la ruta relativa original.

Para backups incrementales, importar después del último backup full aplicado.
"""


def _alembic_version(db: Session) -> str | None:
    try:
        return db.execute(select_text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:
        return None


def select_text(sql: str):
    from sqlalchemy import text

    return text(sql)


def _export_table_csv(db: Session, model, tenant_id: str, since: datetime | None) -> tuple[str, int]:
    table = model.__table__
    query = select(table).where(table.c.tenant_id == tenant_id)
    date_col = INCREMENTAL_DATE_COLUMNS.get(table.name)
    if since is not None and date_col is not None:
        query = query.where(table.c[date_col] > since)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([c.name for c in table.columns])
    count = 0
    for row in db.execute(query):
        writer.writerow([
            v.isoformat() if isinstance(v, datetime) else v for v in row
        ])
        count += 1
    return buf.getvalue(), count


def generate_backup(
    session_factory: sessionmaker, s3, bucket: str, job_id: int
) -> None:
    with session_factory() as db:
        job = db.get(BackupJob, job_id)
        tenant_id = job.tenant_id
        backup_type = job.type
        job.status = "running"
        db.commit()

    since: datetime | None = None
    try:
        with session_factory() as db:
            if backup_type == "incremental":
                since = db.scalar(
                    select(BackupJob.created_at)
                    .where(
                        (BackupJob.tenant_id == tenant_id)
                        & (BackupJob.status == "done")
                        & (BackupJob.id != job_id)
                    )
                    .order_by(BackupJob.created_at.desc())
                    .limit(1)
                )

            counts: dict[str, int] = {}
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp_path = tmp.name

            with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                # 1) datos
                for model in EXPORT_MODELS:
                    name = model.__table__.name
                    content, count = _export_table_csv(db, model, tenant_id, since)
                    zf.writestr(f"data/{name}.csv", content)
                    counts[name] = count

                # 2) archivos desde S3
                files_q = select(MessageFile).where(
                    (MessageFile.tenant_id == tenant_id)
                    & (MessageFile.status == "ok")
                    & MessageFile.s3_key.is_not(None)
                )
                if since is not None:
                    files_q = files_q.where(MessageFile.downloaded_at > since)
                files_count = 0
                for mf in db.scalars(files_q):
                    filename = mf.s3_key.rsplit("/", 1)[-1]
                    arcname = f"files/{mf.message_id}/{mf.file_type}/{filename}"
                    try:
                        obj = s3.get_object(Bucket=bucket, Key=mf.s3_key)
                        zf.writestr(arcname, obj["Body"].read())
                        files_count += 1
                    except Exception:
                        logger.warning("[%s] no se pudo incluir %s en el backup",
                                       tenant_id, mf.s3_key)

                # 3) manifest + README
                manifest = {
                    "tenant_id": tenant_id,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "type": backup_type,
                    "incremental_since": since.isoformat() if since else None,
                    "schema_version": _alembic_version(db),
                    "table_order": [m.__table__.name for m in EXPORT_MODELS],
                    "row_counts": counts,
                    "files_included": files_count,
                }
                zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
                zf.writestr("README.md", README)

        key = backup_key(tenant_id, job_id)
        size = os.path.getsize(tmp_path)
        with open(tmp_path, "rb") as f:
            s3.upload_fileobj(f, bucket, key)
        os.unlink(tmp_path)

        with session_factory() as db:
            job = db.get(BackupJob, job_id)
            job.status = "done"
            job.s3_key_result = key
            job.size_bytes = size
            job.finished_at = datetime.now(UTC)
            job.expires_at = datetime.now(UTC) + timedelta(days=BACKUP_TTL_DAYS)
            db.commit()
        logger.info("[%s] backup %s generado (%d bytes)", tenant_id, job_id, size)

    except Exception as e:
        logger.exception("Backup %s falló", job_id)
        with session_factory() as db:
            job = db.get(BackupJob, job_id)
            job.status = "failed"
            job.error_summary = str(e)[:500]
            job.finished_at = datetime.now(UTC)
            db.commit()


def process_pending_backup_jobs(session_factory: sessionmaker, s3, bucket: str) -> int:
    done = 0
    while True:
        with session_factory() as db:
            job = db.scalars(
                select(BackupJob)
                .where(BackupJob.status == "pending")
                .order_by(BackupJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if job is None:
                return done
            job_id = job.id
            job.status = "running"
            db.commit()
        generate_backup(session_factory, s3, bucket, job_id)
        done += 1
