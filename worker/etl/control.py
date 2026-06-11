"""Ventana deslizante por (tenant, endpoint) — etl_control ahora es POR TENANT (§5.2)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import EtlControl


def get_last_ts(db: Session, tenant_id: str, endpoint: str) -> datetime | None:
    row = db.get(EtlControl, (tenant_id, endpoint))
    if row is None or row.last_ts is None:
        return None
    ts = row.last_ts
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def set_last_ts(db: Session, tenant_id: str, endpoint: str, ts: datetime) -> None:
    row = db.get(EtlControl, (tenant_id, endpoint))
    if row is None:
        db.add(EtlControl(tenant_id=tenant_id, endpoint=endpoint, last_ts=ts))
    else:
        row.last_ts = ts


def get_window(
    last_ts: datetime | None,
    *,
    initial_ts: datetime | None,
    window_days: int,
    now: datetime | None = None,
) -> tuple[datetime, datetime]:
    """from = last_ts (o initial_ts la primera vez); to = min(from + window, now).

    Ventanas de más de ~1 mes devuelven 400 en Botmaker (§11.2): window_days
    debe ser ≤31 (validado en la API de settings).
    """
    now = now or datetime.now(UTC)
    from_dt = last_ts or initial_ts or (now - timedelta(days=window_days))
    if window_days > 0:
        to_dt = min(from_dt + timedelta(days=window_days), now)
    else:
        to_dt = now
    return from_dt, to_dt


def iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_z_ms(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
