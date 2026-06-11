"""Backup / exportación al cliente (§7.4): jobs asíncronos que generan un ZIP en S3."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, DbDep, get_managed_tenant, require_admin
from app.models import BackupJob
from app.services.audit import audit
from app.services.s3 import presign_get

router = APIRouter(prefix="/backups", tags=["backups"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ManagedTenantDep = Annotated[str, Depends(get_managed_tenant)]


class BackupCreate(BaseModel):
    type: str = Field(default="full", pattern=r"^(full|incremental)$")


class BackupOut(BaseModel):
    id: int
    tenant_id: str
    type: str
    status: str
    size_bytes: int | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    error_summary: str | None

    model_config = {"from_attributes": True}


class BackupDownloadOut(BaseModel):
    url: str
    expires_in: int


@router.post("", response_model=BackupOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backup(
    body: BackupCreate, db: DbDep, current: AdminDep, tenant: ManagedTenantDep
):
    running = await db.scalar(
        select(BackupJob.id).where(
            (BackupJob.tenant_id == tenant) & BackupJob.status.in_(("pending", "running"))
        )
    )
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya hay un backup en curso")

    job = BackupJob(tenant_id=tenant, requested_by=current.id, type=body.type, status="pending")
    db.add(job)
    await audit(db, action="backup_requested", tenant_id=tenant, user_id=current.id,
                entity="backup_job", detail={"type": body.type})
    await db.commit()
    await db.refresh(job)
    return job


@router.get("", response_model=list[BackupOut])
async def list_backups(
    db: DbDep, current: AdminDep, tenant: ManagedTenantDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    jobs = await db.scalars(
        select(BackupJob)
        .where(BackupJob.tenant_id == tenant)
        .order_by(BackupJob.created_at.desc())
        .limit(limit)
    )
    return jobs.all()


@router.get("/{backup_id}/download", response_model=BackupDownloadOut)
async def download_backup(
    backup_id: int, db: DbDep, current: AdminDep, tenant: ManagedTenantDep
):
    job = await db.get(BackupJob, backup_id)
    if job is None or job.tenant_id != tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Backup inexistente")
    if job.status != "done" or not job.s3_key_result:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Backup no disponible ({job.status})")

    url = presign_get(job.s3_key_result, filename=f"backup-{tenant}-{backup_id}.zip")
    # Auditar toda descarga de backup (§7.4 / §8.5)
    await audit(db, action="backup_downloaded", tenant_id=tenant, user_id=current.id,
                entity="backup_job", entity_id=str(backup_id))
    await db.commit()

    from app.core.config import get_settings

    return BackupDownloadOut(url=url, expires_in=get_settings().presign_ttl_seconds)
