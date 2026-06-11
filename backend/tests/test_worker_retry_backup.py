"""Tests del job de reintento de fallidas y del generador de backups."""

import io
import json
import zipfile
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from tests.fake_botmaker import PNG, FakeBotmakerSession, FakeResponse, make_client


@pytest.fixture(scope="module")
def session_factory(database):
    return sessionmaker(database, expire_on_commit=False)


def test_retry_failed_files_recupera_archivos(session_factory, s3_mock, database):
    from app.models import MessageFile
    from worker.etl.retry import retry_failed_files, snapshot_counts

    url = "https://storage.botmaker.com/tA/mA6.png"  # forbidden en el seed
    s = FakeBotmakerSession()
    s.route("GET", url, lambda u, p, h: FakeResponse(
        200, content=PNG, headers={"Content-Type": "image/png"}))
    client = make_client(s)

    with session_factory() as db:
        before = snapshot_counts(db, "tA")
        assert before.get("forbidden") == 1

        processed = retry_failed_files(
            db, s3_mock, get_settings().s3_bucket, client, "tA",
            statuses=["forbidden"], limit=10,
        )
        assert processed == 1

        after = snapshot_counts(db, "tA")
        assert after.get("forbidden") is None
        assert after["ok"] == before["ok"] + 1

        mf = db.get(MessageFile, ("tA", "mA6", "media"))
        assert mf.status == "ok"
        assert mf.s3_key == "tenants/tA/files/mA6/media/mA6.png"

    obj = s3_mock.get_object(Bucket=get_settings().s3_bucket, Key=mf.s3_key)
    assert obj["Body"].read() == PNG

    # restaurar el estado para otros tests del módulo
    with session_factory() as db:
        mf = db.get(MessageFile, ("tA", "mA6", "media"))
        mf.status = "forbidden"
        mf.s3_key = None
        db.commit()


def test_process_pending_retry_jobs(session_factory, s3_mock, monkeypatch):
    from app.models import MessageFile, RetryJob
    from worker.etl import retry as retry_mod

    url = "https://storage.botmaker.com/tA/mA6.png"
    s = FakeBotmakerSession()
    s.route("GET", url, lambda u, p, h: FakeResponse(
        200, content=PNG, headers={"Content-Type": "image/png"}))
    monkeypatch.setattr(
        retry_mod, "build_client_for_tenant",
        lambda factory, settings_row: make_client(s),
    )

    # drenar jobs encolados por los tests de la API y dejar mA6 en forbidden
    retry_mod.process_pending_retry_jobs(session_factory, s3_mock, get_settings().s3_bucket)
    with session_factory() as db:
        mf = db.get(MessageFile, ("tA", "mA6", "media"))
        mf.status = "forbidden"
        mf.s3_key = None
        db.commit()

    with session_factory() as db:
        job = RetryJob(tenant_id="tA", filters={"statuses": ["forbidden"], "limit": 5},
                       status="pending")
        db.add(job)
        db.commit()
        job_id = job.id

    n = retry_mod.process_pending_retry_jobs(
        session_factory, s3_mock, get_settings().s3_bucket
    )
    assert n == 1

    with session_factory() as db:
        job = db.get(RetryJob, job_id)
    assert job.status == "done"
    assert job.processed == 1
    assert job.counts_before.get("forbidden") == 1
    assert job.counts_after.get("forbidden") is None
    assert job.finished_at is not None


def test_backup_full_genera_zip_restaurable(session_factory, s3_mock, database):
    from app.models import BackupJob
    from worker.etl.backup import process_pending_backup_jobs

    # drenar jobs encolados por los tests de la API
    process_pending_backup_jobs(session_factory, s3_mock, get_settings().s3_bucket)

    with session_factory() as db:
        job = BackupJob(tenant_id="tA", type="full", status="pending")
        db.add(job)
        db.commit()
        job_id = job.id

    n = process_pending_backup_jobs(session_factory, s3_mock, get_settings().s3_bucket)
    assert n == 1

    with session_factory() as db:
        job = db.get(BackupJob, job_id)
    assert job.status == "done"
    assert job.s3_key_result == f"tenants/tA/backups/{job.id}.zip"
    assert job.size_bytes and job.size_bytes > 0
    assert job.expires_at is not None

    raw = s3_mock.get_object(
        Bucket=get_settings().s3_bucket, Key=job.s3_key_result
    )["Body"].read()
    zf = zipfile.ZipFile(io.BytesIO(raw))
    names = set(zf.namelist())

    assert "manifest.json" in names
    assert "README.md" in names
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["tenant_id"] == "tA"
    assert manifest["type"] == "full"
    assert manifest["row_counts"]["messages"] == 6
    assert manifest["row_counts"]["agent_metrics"] == 4

    # CSV con solo filas del tenant (aislamiento también en el backup)
    chats_csv = zf.read("data/chats.csv").decode()
    assert "5491100000001" in chats_csv
    assert "5492200000001" not in chats_csv  # chat de tB NO debe estar

    # archivos incluidos con la estructura files/{message_id}/{file_type}/
    assert "files/mA3/media/mA3.png" in names


def test_backup_incremental_solo_lo_nuevo(session_factory, s3_mock):
    from app.models import BackupJob, Message
    from worker.etl.backup import process_pending_backup_jobs

    # mensaje nuevo posterior al backup full anterior
    with session_factory() as db:
        db.add(Message(
            tenant_id="tA", id="mA-nuevo", creation_time=datetime.now(UTC),
            message_from="user", chat_id="5491100000001", session_id="s-nuevo",
        ))
        db.add(BackupJob(tenant_id="tA", type="incremental", status="pending"))
        db.commit()

    process_pending_backup_jobs(session_factory, s3_mock, get_settings().s3_bucket)

    with session_factory() as db:
        job = db.scalars(
            select(BackupJob).where(
                (BackupJob.tenant_id == "tA") & (BackupJob.type == "incremental")
            ).order_by(BackupJob.created_at.desc())
        ).first()
        # limpieza del mensaje agregado
        msg = db.get(Message, ("tA", "mA-nuevo"))
        db.delete(msg)
        db.commit()

    assert job.status == "done"
    raw = s3_mock.get_object(
        Bucket=get_settings().s3_bucket, Key=job.s3_key_result
    )["Body"].read()
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("manifest.json"))
    assert manifest["incremental_since"] is not None
    assert manifest["row_counts"]["messages"] == 1  # solo el nuevo
    assert manifest["files_included"] == 0


def test_etl_is_due():
    from worker.main import etl_is_due

    now = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)
    cron = "0 3 * * *"  # 03:00 todos los días
    assert etl_is_due(cron, None, now) is True
    assert etl_is_due(cron, datetime(2026, 5, 9, 3, 1, tzinfo=UTC), now) is True
    assert etl_is_due(cron, datetime(2026, 5, 10, 3, 1, tzinfo=UTC), now) is False
    assert etl_is_due("cron inválido", None, now) is False
