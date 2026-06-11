# Koala — Plataforma SaaS de archivo y análisis de chats de WhatsApp (Botmaker)

Servicio multi-tenant para aseguradoras: archiva **todas** las conversaciones y archivos
del chatbot de WhatsApp (Botmaker borra el histórico), y los expone en un portal web con
dashboards, visor de conversaciones, gestión de descargas fallidas y exportación/backup.

> Plan de desarrollo completo: [PLAN-APP.md](PLAN-APP.md). ETL legacy de referencia: `etl-legacy/`.

## Arquitectura

```
┌────────────┐   cron por tenant   ┌──────────────┐
│  Botmaker  │ ◄────────────────── │   worker/    │──► PostgreSQL (RDS)
│  API v2.0  │   throttle/backoff  │  ETL + jobs  │──► S3 (archivos media)
└────────────┘                     └──────────────┘
                                          ▲ retry_jobs / backup_jobs
┌────────────┐      JWT + tenant_id      ┌──────────────┐
│ frontend/  │ ────────────────────────► │   backend/   │──► PostgreSQL
│ React+Vite │   URLs prefirmadas S3     │   FastAPI    │──► S3 (presign ≤5 min)
└────────────┘                           └──────────────┘
```

- **backend/** — FastAPI + SQLAlchemy 2 async. Auth JWT (access 15 min / refresh 7 días,
  argon2). Scoping multi-tenant SIEMPRE desde el token (superadmin pasa `?tenant_id=`).
- **worker/** — ETL multi-tenant (APScheduler): port completo del ETL legacy con ventana
  deslizante por (tenant, endpoint), rate-limit 1.2 s, backoff 429/5xx, refresh de token
  con rotación persistida, descarga de media a S3. Procesa también los jobs de reintento
  de fallidas y de backup encolados desde la API.
- **frontend/** — React 18 + TS + Vite + Tailwind + TanStack Query + Recharts. UI en español.
- **infra/** — Dockerfiles y deploy. Dev: `docker-compose` con postgres + minio.

## Desarrollo

### Con Docker (recomendado)

```bash
docker compose up
```

Levanta postgres, minio (S3), backend (con migraciones + seed automático), worker y
frontend. Portal: http://localhost:5173 · API docs: http://localhost:8000/api/docs

### Sin Docker

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
./backend/scripts/dev_pg.sh start          # Postgres local en :54330 sin root
cd backend
export DATABASE_URL=postgresql+asyncpg://koala@127.0.0.1:54330/koala
ALEMBIC_DATABASE_URL=postgresql+psycopg://koala@127.0.0.1:54330/koala ../.venv/bin/alembic upgrade head
../.venv/bin/python -m app.seed            # 2 tenants de prueba con ~300 chats c/u
../.venv/bin/uvicorn app.main:app --reload # API en :8000
cd ../frontend && npm install && npm run dev
```

### Usuarios del seed

| Email | Password | Rol |
|---|---|---|
| admin@koala.app | Admin1234! | superadmin |
| admin@gruporimoldi.com | Rimoldi1234! | tenant_admin (GrupoRimoldi) |
| viewer@gruporimoldi.com | Rimoldi1234! | viewer (GrupoRimoldi) |
| admin@demo.com | Demo1234! | tenant_admin (AseguradoraDemo) |
| viewer@demo.com | Demo1234! | viewer (AseguradoraDemo) |

### Tests

```bash
.venv/bin/pytest          # usa Postgres real (levanta cluster local) + S3 mockeado (moto)
.venv/bin/ruff check backend worker
```

Incluyen: tests de fuga cross-tenant (§8.1), métricas con números calculados a mano,
corrida completa del ETL contra un Botmaker falso, reintentos y backups restaurables.

## Operación y deploy

- [docs/deploy-aws.md](docs/deploy-aws.md) — deploy v1 en AWS (EC2 + RDS + S3 + HTTPS).
- [docs/operacion.md](docs/operacion.md) — runbook: alta de tenants, monitoreo del ETL,
  reintentos, backups, rotación de claves.

## Variables de entorno

Ver [.env.example](.env.example). Las críticas: `DATABASE_URL`, `S3_*`, `JWT_SECRET`,
`CREDENTIALS_ENCRYPTION_KEY` (Fernet — cifra las credenciales Botmaker de cada tenant).
