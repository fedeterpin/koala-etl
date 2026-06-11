"""Métricas de dashboards (§7.1, espec extraída del .pbix del cliente).

Reglas heredadas del reporte real:
- "Promedio sin ceros": los promedios de tiempos excluyen NULL **y** 0
  (las sesiones abiertas tienen métricas NULL — trampa §11.6).
- Fechas guardadas en UTC; agrupación por día/mes en hora argentina (§11.8).
- context=siniestros: condición configurable por tenant (cola o botón, §7.1).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.api.deps import CurrentUserDep, DbDep, TenantScopeDep
from app.models import TenantSettings

router = APIRouter(prefix="/metrics", tags=["metrics"])

TZ_ARG = "America/Argentina/Buenos_Aires"

CommonFrom = Annotated[datetime | None, Query(alias="from")]
CommonTo = Annotated[datetime | None, Query(alias="to")]
CommonAgent = Annotated[str | None, Query()]
CommonQueue = Annotated[str | None, Query()]
CommonContext = Annotated[str, Query(pattern="^(general|siniestros)$")]
Granularity = Annotated[str, Query(pattern="^(month|day)$")]


async def _siniestros_config(db, tenant: str) -> tuple[str | None, str | None]:
    settings = await db.get(TenantSettings, tenant)
    if settings is None or (not settings.siniestros_queue and not settings.siniestros_button):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "El tenant no tiene configurada la condición de siniestros",
        )
    return settings.siniestros_queue, settings.siniestros_button


async def _build_filters(
    db,
    tenant: str,
    *,
    alias: str,
    date_col: str,
    date_from: datetime | None,
    date_to: datetime | None,
    agent_id: str | None,
    queue: str | None,
    queue_col: str,
    context: str,
) -> tuple[str, dict]:
    """WHERE común. `alias` es 'am' (agent_metrics) o 'm' (messages)."""
    conds = [f"{alias}.tenant_id = :tenant"]
    params: dict = {"tenant": tenant, "tz": TZ_ARG}
    if date_from is not None:
        conds.append(f"{alias}.{date_col} >= :date_from")
        params["date_from"] = date_from
    if date_to is not None:
        conds.append(f"{alias}.{date_col} <= :date_to")
        params["date_to"] = date_to
    if agent_id:
        conds.append(f"{alias}.agent_id = :agent_id")
        params["agent_id"] = agent_id
    if queue:
        conds.append(f"{alias}.{queue_col} = :queue")
        params["queue"] = queue
    if context == "siniestros":
        sq, sb = await _siniestros_config(db, tenant)
        params["sq"], params["sb"] = sq, sb
        session_col = "session_id" if alias == "m" else "session_id"
        conds.append(
            f"((:sq)::text IS NOT NULL AND {alias}.{queue_col} = :sq "
            f"OR (:sb)::text IS NOT NULL AND EXISTS ("
            f"  SELECT 1 FROM messages mm "
            f"  JOIN message_content mmc ON mmc.tenant_id = mm.tenant_id AND mmc.message_id = mm.id "
            f"  WHERE mm.tenant_id = {alias}.tenant_id AND mm.session_id = {alias}.{session_col} "
            f"    AND mmc.selected_button = :sb))"
        )
    return " AND ".join(conds), params


def _period_expr(alias: str, col: str, granularity: str) -> str:
    fmt = "YYYY-MM" if granularity == "month" else "YYYY-MM-DD"
    return f"to_char({alias}.{col} AT TIME ZONE :tz, '{fmt}')"


@router.get("/summary")
async def summary(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
):
    where_am, params = await _build_filters(
        db, tenant, alias="am", date_col="session_creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue", context=context,
    )
    row = (await db.execute(text(f"""
        SELECT
            count(*)                                          AS total_sessions,
            count(DISTINCT am.chat_id)                        AS unique_clients,
            avg(am.from_op_assigned_to_op_first_response / 60.0)
                FILTER (WHERE am.from_op_assigned_to_op_first_response > 0)
                                                              AS avg_first_response_min,
            count(*) FILTER (WHERE am.agent_id IS NULL)       AS sessions_no_agent
        FROM agent_metrics am
        WHERE {where_am}
    """), params)).one()

    where_m, params_m = await _build_filters(
        db, tenant, alias="m", date_col="creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue_id", context=context,
    )
    msg_row = (await db.execute(text(f"""
        SELECT
            count(*) FILTER (WHERE m.whatsapp_template_name IS NOT NULL) AS templates_sent,
            count(DISTINCT m.session_id) FILTER (WHERE first_from = 'user') AS sessions_started_by_external
        FROM (
            SELECT m.*, first_value(m.message_from) OVER (
                PARTITION BY m.tenant_id, m.session_id ORDER BY m.creation_time
            ) AS first_from
            FROM messages m
            WHERE {where_m}
        ) m
    """), params_m)).one()

    total = row.total_sessions or 0
    no_agent = row.sessions_no_agent or 0
    return {
        "total_sessions": total,
        "unique_clients": row.unique_clients or 0,
        "avg_first_response_min": round(float(row.avg_first_response_min), 2)
        if row.avg_first_response_min is not None else None,
        "sessions_no_agent": no_agent,
        "pct_sessions_no_agent": round(100.0 * no_agent / total, 2) if total else 0.0,
        "templates_sent": msg_row.templates_sent or 0,
        "sessions_started_by_external": msg_row.sessions_started_by_external or 0,
    }


@router.get("/sessions-by-month")
async def sessions_by_month(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
    by_agent: bool = False,
    granularity: Granularity = "month",
):
    where, params = await _build_filters(
        db, tenant, alias="am", date_col="session_creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue", context=context,
    )
    period = _period_expr("am", "session_creation_time", granularity)
    agent_sel = ", coalesce(am.agent_name, '(sin agente)') AS agent_name" if by_agent else ""
    agent_grp = ", 2" if by_agent else ""
    rows = await db.execute(text(f"""
        SELECT {period} AS period{agent_sel}, count(*) AS sessions
        FROM agent_metrics am
        WHERE {where} AND am.session_creation_time IS NOT NULL
        GROUP BY 1{agent_grp}
        ORDER BY 1
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/sessions-by-agent")
async def sessions_by_agent(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
):
    where, params = await _build_filters(
        db, tenant, alias="am", date_col="session_creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue", context=context,
    )
    rows = await db.execute(text(f"""
        SELECT coalesce(am.agent_name, '(sin agente)') AS agent_name,
               am.agent_id,
               count(*) AS sessions,
               count(DISTINCT am.chat_id) AS clients
        FROM agent_metrics am
        WHERE {where}
        GROUP BY 1, 2
        ORDER BY sessions DESC
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/clients-by-month")
async def clients_by_month(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
    by_agent: bool = False,
    granularity: Granularity = "month",
):
    where, params = await _build_filters(
        db, tenant, alias="am", date_col="session_creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue", context=context,
    )
    period = _period_expr("am", "session_creation_time", granularity)
    agent_sel = ", coalesce(am.agent_name, '(sin agente)') AS agent_name" if by_agent else ""
    agent_grp = ", 2" if by_agent else ""
    rows = await db.execute(text(f"""
        SELECT {period} AS period{agent_sel}, count(DISTINCT am.chat_id) AS clients
        FROM agent_metrics am
        WHERE {where} AND am.session_creation_time IS NOT NULL
        GROUP BY 1{agent_grp}
        ORDER BY 1
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/first-response-by-agent")
async def first_response_by_agent(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
):
    """Promedio de minutos asignación→primera respuesta por agente, sin ceros ni NULL."""
    where, params = await _build_filters(
        db, tenant, alias="am", date_col="session_creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue", context=context,
    )
    rows = await db.execute(text(f"""
        SELECT am.agent_name,
               round(avg(am.from_op_assigned_to_op_first_response / 60.0)::numeric, 2) AS avg_minutes,
               count(*) AS sessions_considered
        FROM agent_metrics am
        WHERE {where}
          AND am.agent_name IS NOT NULL
          AND am.from_op_assigned_to_op_first_response > 0
        GROUP BY 1
        ORDER BY avg_minutes DESC
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/templates-by-month")
async def templates_by_month(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
    granularity: Granularity = "month",
):
    where, params = await _build_filters(
        db, tenant, alias="m", date_col="creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue_id", context=context,
    )
    period = _period_expr("m", "creation_time", granularity)
    rows = await db.execute(text(f"""
        SELECT {period} AS period, m.whatsapp_template_name AS template, count(*) AS sent
        FROM messages m
        WHERE {where} AND m.whatsapp_template_name IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/button-segmentation")
async def button_segmentation(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
):
    where, params = await _build_filters(
        db, tenant, alias="m", date_col="creation_time",
        date_from=date_from, date_to=date_to, agent_id=agent_id,
        queue=queue, queue_col="queue_id", context=context,
    )
    rows = await db.execute(text(f"""
        SELECT mc.selected_button AS button,
               count(*) AS times_selected,
               count(DISTINCT m.session_id) AS sessions
        FROM messages m
        JOIN message_content mc
          ON mc.tenant_id = m.tenant_id AND mc.message_id = m.id
        WHERE {where} AND mc.selected_button IS NOT NULL
        GROUP BY 1
        ORDER BY times_selected DESC
    """), params)
    return {"items": [dict(r._mapping) for r in rows]}


@router.get("/contact-rankings")
async def contact_rankings(
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
    kind: Annotated[str, Query(pattern="^(sessions|messages|external|templates)$")] = "sessions",
    date_from: CommonFrom = None,
    date_to: CommonTo = None,
    agent_id: CommonAgent = None,
    queue: CommonQueue = None,
    context: CommonContext = "general",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    if kind == "sessions":
        where, params = await _build_filters(
            db, tenant, alias="am", date_col="session_creation_time",
            date_from=date_from, date_to=date_to, agent_id=agent_id,
            queue=queue, queue_col="queue", context=context,
        )
        inner = f"""
            SELECT am.chat_id, count(*) AS value
            FROM agent_metrics am
            WHERE {where} AND am.chat_id IS NOT NULL
            GROUP BY 1
        """
    else:
        where, params = await _build_filters(
            db, tenant, alias="m", date_col="creation_time",
            date_from=date_from, date_to=date_to, agent_id=agent_id,
            queue=queue, queue_col="queue_id", context=context,
        )
        if kind == "messages":
            inner = f"""
                SELECT m.chat_id, count(*) AS value
                FROM messages m
                WHERE {where} AND m.chat_id IS NOT NULL
                GROUP BY 1
            """
        elif kind == "templates":
            inner = f"""
                SELECT m.chat_id, count(*) AS value
                FROM messages m
                WHERE {where} AND m.chat_id IS NOT NULL
                  AND m.whatsapp_template_name IS NOT NULL
                GROUP BY 1
            """
        else:  # external: sesiones iniciadas por el cliente
            inner = f"""
                SELECT chat_id, count(*) AS value FROM (
                    SELECT DISTINCT ON (m.tenant_id, m.session_id)
                           m.chat_id, m.message_from
                    FROM messages m
                    WHERE {where} AND m.chat_id IS NOT NULL AND m.session_id IS NOT NULL
                    ORDER BY m.tenant_id, m.session_id, m.creation_time
                ) firsts
                WHERE message_from = 'user'
                GROUP BY 1
            """

    params["limit"] = limit
    rows = await db.execute(text(f"""
        SELECT r.chat_id,
               cd.first_name,
               cd.last_name,
               r.value
        FROM ({inner}) r
        LEFT JOIN chat_details cd
          ON cd.tenant_id = :tenant AND cd.chat_id = r.chat_id
        ORDER BY r.value DESC
        LIMIT :limit
    """), params)
    return {"kind": kind, "items": [dict(r._mapping) for r in rows]}
