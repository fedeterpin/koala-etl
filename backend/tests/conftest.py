"""Config de tests: DB Postgres real (cluster local o CI), S3 mockeado con moto.

El dataset de prueba es chico y calculado a mano para poder afirmar números
exactos en las métricas (ver factories.py).
"""

import os
import subprocess
from pathlib import Path

# ——— Entorno ANTES de importar la app (get_settings está cacheado) ———

REPO_ROOT = Path(__file__).resolve().parents[2]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://koala@127.0.0.1:54330/koala_test"
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "secreto-de-tests-suficientemente-largo-1234"
os.environ["CREDENTIALS_ENCRYPTION_KEY"] = "2eyREgnFTBSrSJ6BMu_N_DhdJZAEy3wDR1NTHwt0Y2g="
os.environ["S3_BUCKET"] = "koala-test-bucket"
os.environ["S3_ACCESS_KEY"] = "testing"
os.environ["S3_SECRET_KEY"] = "testing"
os.environ["S3_ENDPOINT_URL"] = ""
# moto usa las credenciales estándar de AWS
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

import httpx  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import app.db.base as dbase  # noqa: E402
from app.core.config import get_settings  # noqa: E402

SYNC_URL = TEST_DATABASE_URL.replace("+asyncpg", "+psycopg")


def _ensure_database() -> None:
    """Si no hay Postgres accesible, intenta levantar el cluster local de dev."""
    try:
        create_engine(SYNC_URL, poolclass=NullPool).connect().close()
    except Exception:
        subprocess.run(
            [str(REPO_ROOT / "backend/scripts/dev_pg.sh"), "start"],
            check=True, capture_output=True,
        )
        create_engine(SYNC_URL, poolclass=NullPool).connect().close()


@pytest.fixture(scope="session", autouse=True)
def database():
    """Esquema desde cero vía migraciones Alembic (valida que sean reproducibles)."""
    _ensure_database()
    engine = create_engine(SYNC_URL, poolclass=NullPool)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    env = os.environ.copy()
    env["ALEMBIC_DATABASE_URL"] = SYNC_URL
    subprocess.run(
        [str(REPO_ROOT / ".venv/bin/alembic"), "upgrade", "head"],
        cwd=REPO_ROOT / "backend", env=env, check=True, capture_output=True,
    )
    yield engine
    engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def s3_mock():
    with mock_aws():
        from app.services.s3 import get_s3_client

        get_s3_client.cache_clear()
        client = get_s3_client()
        client.create_bucket(Bucket=get_settings().s3_bucket)
        yield client
        get_s3_client.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def seed(database, s3_mock):
    from tests.factories import seed_test_data

    seed_test_data(database, s3_mock, get_settings().s3_bucket)


@pytest.fixture(autouse=True)
def _null_pool_engine():
    """Pool nulo: cada request abre/cierra conexión en su propio event loop."""
    if dbase._engine is None:
        dbase._engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        dbase._session_factory = None
    yield


@pytest.fixture
async def client():
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def login(client: httpx.AsyncClient, email: str, password: str = "Test1234!") -> dict:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    return {"Authorization": f"Bearer {data['access_token']}"}


@pytest.fixture
async def sa_headers(client):
    return await login(client, "sa@test.com")


@pytest.fixture
async def a_admin_headers(client):
    return await login(client, "a-admin@test.com")


@pytest.fixture
async def a_viewer_headers(client):
    return await login(client, "a-viewer@test.com")


@pytest.fixture
async def b_admin_headers(client):
    return await login(client, "b-admin@test.com")
