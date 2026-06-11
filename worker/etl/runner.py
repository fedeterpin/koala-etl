"""Orquestador del ETL por tenant: etapas aisladas + registro en etl_runs (§6).

Si una etapa falla se loguea en etl_stage_errors y se continúa con la siguiente
(igual que el _run_stage legacy). El estado final es ok / partial / failed.
"""

import logging
from datetime import UTC, datetime

import requests
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models import EtlRun, EtlStageError, Tenant, TenantSettings
from worker.etl.botmaker import BotmakerClient
from worker.etl.stages import (
    StageContext,
    stage_agent_metrics,
    stage_agent_performance,
    stage_chat_details,
    stage_messages,
)

logger = logging.getLogger("koala.worker.runner")

STAGES = [
    ("agent_performance", stage_agent_performance),
    ("agent_metrics", stage_agent_metrics),
    ("messages", stage_messages),
    ("chat_details", stage_chat_details),
]


def build_client_for_tenant(
    session_factory: sessionmaker,
    settings_row: TenantSettings,
    *,
    http_session=None,
    min_interval: float | None = None,
) -> BotmakerClient:
    app_settings = get_settings()

    def persist_rotated_tokens(access_token: str, refresh_token: str) -> None:
        # Sesión propia y commit inmediato: si la etapa luego falla, la rotación
        # ya quedó persistida (§11.1 — el refresh token rota y no se recupera).
        with session_factory() as db:
            row = db.get(TenantSettings, settings_row.tenant_id)
            row.botmaker_token_enc = encrypt_secret(access_token)
            row.botmaker_refresh_token_enc = encrypt_secret(refresh_token)
            db.commit()

    return BotmakerClient(
        client_id=settings_row.botmaker_client_id or "",
        secret_id=settings_row.botmaker_secret_id or "",
        access_token=(
            decrypt_secret(settings_row.botmaker_token_enc)
            if settings_row.botmaker_token_enc else ""
        ),
        refresh_token=(
            decrypt_secret(settings_row.botmaker_refresh_token_enc)
            if settings_row.botmaker_refresh_token_enc else ""
        ),
        on_tokens_rotated=persist_rotated_tokens,
        session=http_session,
        min_interval=app_settings.botmaker_min_interval if min_interval is None else min_interval,
        max_retries=app_settings.http_max_retries,
        backoff_base=app_settings.http_backoff_base,
    )


def run_tenant_etl(
    session_factory: sessionmaker,
    s3,
    bucket: str,
    tenant_id: str,
    *,
    client: BotmakerClient | None = None,
    now: datetime | None = None,
) -> int:
    """Corre el ETL completo de un tenant. Devuelve el id de etl_runs."""
    app_settings = get_settings()

    with session_factory() as db:
        settings_row = db.get(TenantSettings, tenant_id)
        tenant = db.get(Tenant, tenant_id)
        if tenant is None or settings_row is None:
            raise ValueError(f"Tenant {tenant_id} sin settings")

        run = EtlRun(tenant_id=tenant_id, started_at=datetime.now(UTC), status="running")
        db.add(run)
        db.commit()
        run_id = run.id

        if client is None:
            client = build_client_for_tenant(session_factory, settings_row)

        ctx = StageContext(
            tenant_id=tenant_id,
            client=client,
            s3=s3,
            bucket=bucket,
            initial_ts=settings_row.etl_initial_ts,
            window_days=settings_row.etl_window_days or app_settings.etl_default_window_days,
            now=now,
        )

    stats: dict = {}
    failures: list[str] = []

    for label, fn in STAGES:
        with session_factory() as db:
            try:
                stage_stats = fn(db, ctx)
                db.commit()
                stats[label] = stage_stats
                logger.info("[%s] etapa %s OK: %s", tenant_id, label, stage_stats)
            except Exception as e:
                db.rollback()
                failures.append(label)
                payload = {"exc_type": type(e).__name__, "message": str(e)[:500]}
                if isinstance(e, requests.HTTPError) and e.response is not None:
                    payload["status"] = e.response.status_code
                logger.exception("[%s] etapa %s falló; continúo", tenant_id, label)
                with session_factory() as errdb:
                    errdb.add(EtlStageError(run_id=run_id, stage=label, payload=payload))
                    errdb.commit()
                stats[label] = {"error": payload["message"]}

    status = "ok" if not failures else ("failed" if len(failures) == len(STAGES) else "partial")
    with session_factory() as db:
        run = db.get(EtlRun, run_id)
        run.finished_at = datetime.now(UTC)
        run.status = status
        run.stats = stats
        run.error_summary = ", ".join(f"etapa {f} falló" for f in failures) or None
        db.commit()

    logger.info("[%s] ETL terminado: %s", tenant_id, status)
    return run_id


def _ensure_session(db: Session) -> None:  # pragma: no cover - helper de tipado
    pass
