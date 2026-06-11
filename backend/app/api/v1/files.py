"""Archivos: URL prefirmada para media del visor (§7.2) y gestión de
descargas fallidas (§7.3)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUser,
    CurrentUserDep,
    DbDep,
    TenantScopeDep,
    get_managed_tenant,
    require_admin,
)
from app.models import MessageFile, RetryJob
from app.services.audit import audit
from app.services.s3 import presign_get

router = APIRouter(prefix="/files", tags=["files"])

AdminDep = Annotated[CurrentUser, Depends(require_admin)]
ManagedTenantDep = Annotated[str, Depends(get_managed_tenant)]

RETRYABLE_STATUSES = ("forbidden", "not_found", "error")


# ——— URL prefirmada para el visor ———

class FileUrlOut(BaseModel):
    url: str
    expires_in: int
    content_type: str | None


@router.get("/{message_id}/{file_type}/url", response_model=FileUrlOut)
async def get_file_url(
    message_id: str,
    file_type: str,
    db: DbDep,
    current: CurrentUserDep,
    tenant: TenantScopeDep,
):
    """Valida pertenencia al tenant y devuelve URL prefirmada S3 (TTL ≤ 5 min)."""
    mf = await db.get(MessageFile, (tenant, message_id, file_type))
    if mf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Archivo inexistente")
    if mf.status != "ok" or not mf.s3_key:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Archivo no descargado ({mf.status})")

    url = presign_get(mf.s3_key)
    await audit(db, action="file_url_generated", tenant_id=tenant, user_id=current.id,
                entity="message_file", entity_id=f"{message_id}/{file_type}")
    await db.commit()

    from app.core.config import get_settings

    return FileUrlOut(
        url=url,
        expires_in=get_settings().presign_ttl_seconds,
        content_type=mf.content_type,
    )


# ——— Gestión de descargas fallidas ———

class FailedFileItem(BaseModel):
    message_id: str
    file_type: str
    status: str
    original_url: str
    downloaded_at: datetime | None


class FailedFilesOut(BaseModel):
    total: int
    page: int
    page_size: int
    counts_by_status: dict[str, int]
    counts_by_type: dict[str, int]
    items: list[FailedFileItem]


@router.get("/failed", response_model=FailedFilesOut)
async def list_failed_files(
    db: DbDep,
    current: AdminDep,
    tenant: ManagedTenantDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    file_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query(alias="from")] = None,
    date_to: Annotated[datetime | None, Query(alias="to")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
):
    base = select(MessageFile).where(
        (MessageFile.tenant_id == tenant) & MessageFile.status.in_(RETRYABLE_STATUSES)
    )
    if status_filter:
        base = base.where(MessageFile.status == status_filter)
    if file_type:
        base = base.where(MessageFile.file_type == file_type)
    if date_from is not None:
        base = base.where(MessageFile.downloaded_at >= date_from)
    if date_to is not None:
        base = base.where(MessageFile.downloaded_at <= date_to)

    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0

    counts_by_status = {
        s: c
        for s, c in await db.execute(
            select(MessageFile.status, func.count())
            .where(MessageFile.tenant_id == tenant)
            .group_by(MessageFile.status)
        )
    }
    counts_by_type = {
        t: c
        for t, c in await db.execute(
            select(MessageFile.file_type, func.count())
            .where(
                (MessageFile.tenant_id == tenant)
                & MessageFile.status.in_(RETRYABLE_STATUSES)
            )
            .group_by(MessageFile.file_type)
        )
    }

    rows = (
        await db.scalars(
            base.order_by(MessageFile.downloaded_at.desc().nulls_last())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    return FailedFilesOut(
        total=total,
        page=page,
        page_size=page_size,
        counts_by_status=counts_by_status,
        counts_by_type=counts_by_type,
        items=[
            FailedFileItem(
                message_id=r.message_id,
                file_type=r.file_type,
                status=r.status,
                original_url=r.original_url,
                downloaded_at=r.downloaded_at,
            )
            for r in rows
        ],
    )


class RetryRequest(BaseModel):
    statuses: list[str] = Field(default=list(RETRYABLE_STATUSES))
    file_types: list[str] | None = None
    message_ids: list[str] | None = None
    limit: int = Field(default=200, ge=1, le=2000)


class RetryJobOut(BaseModel):
    id: int
    tenant_id: str
    status: str
    filters: dict | None
    counts_before: dict | None
    counts_after: dict | None
    processed: int | None
    created_at: datetime
    finished_at: datetime | None
    error_summary: str | None

    model_config = {"from_attributes": True}


@router.post("/retry", response_model=RetryJobOut, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_retry(
    body: RetryRequest, db: DbDep, current: AdminDep, tenant: ManagedTenantDep
):
    invalid = set(body.statuses) - set(RETRYABLE_STATUSES)
    if invalid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Status no reintetable: {invalid}")

    job = RetryJob(
        tenant_id=tenant,
        requested_by=current.id,
        filters=body.model_dump(),
        status="pending",
    )
    db.add(job)
    await audit(db, action="retry_enqueued", tenant_id=tenant, user_id=current.id,
                entity="retry_job")
    await db.commit()
    await db.refresh(job)
    return job


@router.get("/retry-jobs", response_model=list[RetryJobOut])
async def list_retry_jobs(
    db: DbDep, current: AdminDep, tenant: ManagedTenantDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
):
    jobs = await db.scalars(
        select(RetryJob)
        .where(RetryJob.tenant_id == tenant)
        .order_by(RetryJob.created_at.desc())
        .limit(limit)
    )
    return jobs.all()


@router.get("/retry-jobs/{job_id}", response_model=RetryJobOut)
async def get_retry_job(
    job_id: int, db: DbDep, current: AdminDep, tenant: ManagedTenantDep
):
    job = await db.get(RetryJob, job_id)
    if job is None or job.tenant_id != tenant:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job inexistente")
    return job
