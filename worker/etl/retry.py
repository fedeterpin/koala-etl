"""Reintento de descargas fallidas (port de etl_retry_message_files.py, §6.8).

Función reutilizable: la usa el job programado del worker y los jobs encolados
desde la API (§7.3, tabla retry_jobs).
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import MessageFile, RetryJob, TenantSettings
from worker.etl.botmaker import BotmakerClient
from worker.etl.files import download_to_s3
from worker.etl.runner import build_client_for_tenant

logger = logging.getLogger("koala.worker.retry")

RETRYABLE = ("forbidden", "not_found", "error")


def snapshot_counts(db: Session, tenant_id: str) -> dict[str, int]:
    rows = db.execute(
        select(MessageFile.status, func.count())
        .where(MessageFile.tenant_id == tenant_id)
        .group_by(MessageFile.status)
    )
    return {status: count for status, count in rows}


def retry_failed_files(
    db: Session,
    s3,
    bucket: str,
    client: BotmakerClient,
    tenant_id: str,
    *,
    statuses: list[str] | None = None,
    file_types: list[str] | None = None,
    message_ids: list[str] | None = None,
    limit: int = 200,
) -> int:
    """Reintenta el pipeline de descarga para las filas que matcheen. Devuelve procesadas."""
    statuses = [s for s in (statuses or list(RETRYABLE)) if s in RETRYABLE]

    query = select(MessageFile).where(
        (MessageFile.tenant_id == tenant_id) & MessageFile.status.in_(statuses)
    )
    if file_types:
        query = query.where(MessageFile.file_type.in_([t.lower() for t in file_types]))
    if message_ids:
        query = query.where(MessageFile.message_id.in_(message_ids))
    query = query.order_by(
        MessageFile.downloaded_at.asc().nulls_first(), MessageFile.message_id
    ).limit(limit)

    rows = list(db.scalars(query))
    logger.info("[%s] reintentando %d archivos", tenant_id, len(rows))

    processed = 0
    for mf in rows:
        try:
            result = download_to_s3(
                client, s3, bucket,
                url=mf.original_url, tenant_id=tenant_id,
                message_id=mf.message_id, file_type=mf.file_type,
            )
            mf.status = result.status
            mf.s3_key = result.s3_key
            mf.size_bytes = result.size_bytes
            mf.content_type = result.content_type
            mf.downloaded_at = datetime.now(UTC)
            processed += 1
            if processed % 50 == 0:
                db.commit()
        except Exception:
            logger.exception("[%s] fallo reintentando %s/%s",
                             tenant_id, mf.message_id, mf.file_type)
    db.commit()
    return processed


def process_pending_retry_jobs(session_factory: sessionmaker, s3, bucket: str) -> int:
    """Toma jobs `pending` de retry_jobs y los ejecuta. Devuelve cuántos procesó."""
    done = 0
    while True:
        with session_factory() as db:
            job = db.scalars(
                select(RetryJob)
                .where(RetryJob.status == "pending")
                .order_by(RetryJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            ).first()
            if job is None:
                return done

            job.status = "running"
            job.counts_before = snapshot_counts(db, job.tenant_id)
            db.commit()
            job_id, tenant_id, filters = job.id, job.tenant_id, job.filters or {}

        try:
            with session_factory() as db:
                settings_row = db.get(TenantSettings, tenant_id)
                client = build_client_for_tenant(session_factory, settings_row)
                processed = retry_failed_files(
                    db, s3, bucket, client, tenant_id,
                    statuses=filters.get("statuses"),
                    file_types=filters.get("file_types"),
                    message_ids=filters.get("message_ids"),
                    limit=filters.get("limit") or 200,
                )
            with session_factory() as db:
                job = db.get(RetryJob, job_id)
                job.status = "done"
                job.processed = processed
                job.counts_after = snapshot_counts(db, tenant_id)
                job.finished_at = datetime.now(UTC)
                db.commit()
        except Exception as e:
            logger.exception("Retry job %s falló", job_id)
            with session_factory() as db:
                job = db.get(RetryJob, job_id)
                job.status = "failed"
                job.error_summary = str(e)[:500]
                job.finished_at = datetime.now(UTC)
                db.commit()
        done += 1
