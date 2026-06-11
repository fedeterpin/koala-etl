"""Registro de auditoría (§8.5): logins, visualización de conversaciones,
descargas de archivos y backups.

Importante (§8.7 y §11.7): nunca registrar contenido de mensajes ni datos
sensibles en `detail`; solo identificadores.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def audit(
    db: AsyncSession,
    *,
    action: str,
    tenant_id: str | None = None,
    user_id: int | None = None,
    entity: str | None = None,
    entity_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail,
    ))
