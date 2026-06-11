from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Base de datos
    database_url: str = "postgresql+asyncpg://koala:koala@localhost:5432/koala"

    # S3 / MinIO
    s3_endpoint_url: str | None = None  # vacío en AWS real
    s3_bucket: str = "koala-files"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    presign_ttl_seconds: int = 300  # ≤ 5 min (requisito de seguridad)

    # Auth
    jwt_secret: str = "dev-secret"
    jwt_access_ttl: int = 900
    jwt_refresh_ttl: int = 604800
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # Cifrado de credenciales Botmaker
    credentials_encryption_key: str = ""

    # App
    app_base_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"  # separadas por coma
    etl_default_window_days: int = 30
    log_level: str = "INFO"

    # Botmaker (defaults globales; credenciales viven en tenant_settings)
    botmaker_min_interval: float = 1.2
    http_max_retries: int = 6
    http_backoff_base: float = 1.7

    @property
    def database_url_sync(self) -> str:
        """URL síncrona (psycopg) para el worker y Alembic."""
        return self.database_url.replace("+asyncpg", "+psycopg")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
