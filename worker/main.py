"""Proceso worker: scheduler de ETL por tenant + jobs de reintento y backup.

- ETL: cada tenant activo (`tenant_settings.is_etl_enabled`) corre según su
  `etl_schedule_cron`. Se considera "vencido" si el último disparo teórico del
  cron es posterior al inicio de la última corrida registrada en etl_runs.
- retry_jobs / backup_jobs: se procesan por polling (encolados desde la API).
"""

import logging
import time
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from croniter import croniter
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.models import EtlRun, TenantSettings
from app.services.s3 import get_s3_client
from worker.etl.backup import process_pending_backup_jobs
from worker.etl.retry import process_pending_retry_jobs
from worker.etl.runner import run_tenant_etl

logging.basicConfig(
    level=get_settings().log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("koala.worker")


def make_session_factory() -> sessionmaker:
    engine = create_engine(get_settings().database_url_sync, pool_pre_ping=True)
    return sessionmaker(engine, expire_on_commit=False)


def etl_is_due(cron_expr: str, last_run_started: datetime | None, now: datetime) -> bool:
    """True si el último disparo teórico del cron quedó después de la última corrida."""
    try:
        prev_fire = croniter(cron_expr, now).get_prev(datetime)
    except (ValueError, KeyError):
        logger.error("Cron inválido: %r", cron_expr)
        return False
    if prev_fire.tzinfo is None:
        prev_fire = prev_fire.replace(tzinfo=UTC)
    if last_run_started is None:
        return True
    if last_run_started.tzinfo is None:
        last_run_started = last_run_started.replace(tzinfo=UTC)
    return prev_fire > last_run_started


def process_due_etl(session_factory: sessionmaker, s3, bucket: str) -> int:
    now = datetime.now(UTC)
    ran = 0
    with session_factory() as db:
        tenants = list(db.scalars(
            select(TenantSettings).where(TenantSettings.is_etl_enabled.is_(True))
        ))
        last_runs = dict(db.execute(
            select(EtlRun.tenant_id, func.max(EtlRun.started_at)).group_by(EtlRun.tenant_id)
        ))
        # corridas colgadas: si hay una "running" reciente no relanzar
        running = set(db.scalars(
            select(EtlRun.tenant_id).where(
                (EtlRun.status == "running")
                & (EtlRun.started_at > now - timedelta(hours=6))
            )
        ))

    for ts in tenants:
        if ts.tenant_id in running:
            continue
        cron = ts.etl_schedule_cron or "0 3 * * *"
        if not etl_is_due(cron, last_runs.get(ts.tenant_id), now):
            continue
        if not ts.botmaker_token_enc:
            logger.warning("[%s] ETL habilitado pero sin credenciales Botmaker", ts.tenant_id)
            continue
        logger.info("[%s] ETL vencido según cron %r: iniciando", ts.tenant_id, cron)
        try:
            run_tenant_etl(session_factory, s3, bucket, ts.tenant_id)
            ran += 1
        except Exception:
            logger.exception("[%s] corrida de ETL abortó", ts.tenant_id)
    return ran


def main() -> None:
    settings = get_settings()
    session_factory = make_session_factory()
    s3 = get_s3_client()
    bucket = settings.s3_bucket

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        process_due_etl, "interval", seconds=60,
        args=[session_factory, s3, bucket],
        max_instances=1, coalesce=True, id="etl",
    )
    scheduler.add_job(
        process_pending_retry_jobs, "interval", seconds=10,
        args=[session_factory, s3, bucket],
        max_instances=1, coalesce=True, id="retry",
    )
    scheduler.add_job(
        process_pending_backup_jobs, "interval", seconds=20,
        args=[session_factory, s3, bucket],
        max_instances=1, coalesce=True, id="backups",
    )
    scheduler.start()
    logger.info("Worker Koala iniciado (ETL cada 60s, retry 10s, backups 20s)")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
