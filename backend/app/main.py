import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings

settings = get_settings()

logging.basicConfig(level=settings.log_level.upper())

app = FastAPI(
    title="Koala — Archivo y análisis de chats de WhatsApp",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}


def _include_routers() -> None:
    from app.api.v1 import admin, auth, backups, chats, files, metrics

    for module in (auth, admin, metrics, chats, files, backups):
        app.include_router(module.router, prefix="/api/v1")


_include_routers()
