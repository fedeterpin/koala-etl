# Plan de desarrollo — Plataforma SaaS de archivo y análisis de chats de WhatsApp (Botmaker)

> Documento de planificación para construir la aplicación full-stack desde cero.
> Generado a partir del análisis del proyecto ETL existente (`ETL-GrupoRimoldi`) y del
> reporte Power BI real del cliente (`Panel de Control WhatsApp.pbix`).

---

## 1. Contexto del negocio

- El vendor vende a **aseguradoras** un servicio de **resguardo y análisis de las conversaciones
  de su chatbot de WhatsApp (Botmaker)**. Botmaker borra el histórico con el tiempo; este
  producto garantiza que el cliente conserve **todos los chats y archivos** (audios, imágenes,
  documentos) y pueda explorarlos y analizarlos.
- Hoy existe una solución legacy **on-premise por cliente**: un script ETL en Python que corre
  por tarea programada en un Windows Server del cliente, guarda en SQL Server local y descarga
  archivos a disco (`C:\KoalaETL\files`). Los análisis se ven en un Power BI manual.
- **Nuevo modelo (este proyecto):** servicio centralizado en la nube del vendor.
  - El vendor opera el ETL contra Botmaker (credenciales por cliente).
  - Base de datos propia en la nube + archivos en object storage.
  - Portal web multi-tenant donde cada cliente entra y ve **solo sus datos**.
  - Opción de **backup hacia el servidor del cliente** que lo desee (la propuesta de
    "tu copia de los datos" se mantiene como feature de exportación).

## 2. Decisiones ya tomadas (no re-discutir)

| Tema | Decisión |
|---|---|
| Modelo | App **multi-tenant** única (un deploy, N clientes, scoping por `tenant_id`) |
| Nube | **AWS** |
| Base de datos | **PostgreSQL** (RDS). Se migra el esquema desde SQL Server |
| Archivos | **S3** (reemplaza el filesystem local). URLs prefirmadas para servir media |
| ETL | **Refactor completo incluido**: worker multi-tenant en la nube |
| Auth | Usuarios locales con **roles por tenant + admin global del vendor** |
| Alcance v1 | Dashboards + Visor de conversaciones + Gestión de descargas fallidas + Backup/exportación al cliente |
| Branding | Marca única del producto; el tenant ve su nombre/logo en el header. UI en **español** |
| Stack | Backend **Python 3.12 + FastAPI**; Frontend **React 18 + TypeScript + Vite**; ver §4 |

## 3. Material de referencia (en este repo)

| Recurso | Para qué sirve |
|---|---|
| `scripts/etl_botmaker_logs.py` | ETL legacy completo: etapas, ventana deslizante (`etl_control`), rate-limit/backoff/refresh de token de Botmaker, descarga de media con temp-links. **Es la espec funcional del worker nuevo** |
| `scripts/etl_retry_message_files.py` | Lógica de reintento de descargas fallidas (base del módulo de gestión de fallidas) |
| `sql/script creacion esquema KoalaETL.sql` | Esquema legacy SQL Server (18 tablas) a portar a PostgreSQL |
| `sql/Alter status message_files.sql` | Columna `status` + CHECK (`ok/forbidden/not_found/error/skipped`) e índice |
| `sql/vw_agent_metrics_arg.sql` | Vista con fechas en huso argentino (-03:00) usada por los dashboards |
| `sql/datos_prueba.sql` y `sql/datos_prueba_volumen.sql` | Datos de prueba coherentes (en T-SQL; portar como seed de Postgres) |
| `Panel de Control WhatsApp.pbix` | Reporte real del cliente. La espec de dashboards extraída está en §7 |

**Notas de la API de Botmaker (extraídas del ETL legacy, respetar):**
- Base v2.0 `https://api.botmaker.com/v2.0`; header `access-token` (no Bearer).
- Endpoints: `/messages` (paginado `nextPage`, `limit=1500`, `long-term-search`), `/dashboards/agent-performance`, `/dashboards/agent-metrics` (param `session-status` open|closed), `/chats/{chatId}`, `/private-media/temp-access-link` (para media privada con 403).
- Refresh de credenciales: POST `https://go.botmaker.com/api/v1.0/auth/credentials` con headers `clientId/secretId/refreshToken`; responde 200 con `accessToken/refreshToken` nuevos o 204 sin cambio. **El refresh token rota: persistirlo**.
- Rate limit: ~1 req/seg por tenant. Manejar 429 con `Retry-After`, backoff exponencial con jitter, reintento tras 401 con refresh.
- Ventanas de consulta máx ~1 mes (400 si se pide más).

## 4. Stack técnico y arquitectura

### Monorepo

```
/
├── backend/            # FastAPI (API del portal)
│   ├── app/
│   │   ├── api/        # routers por dominio
│   │   ├── core/       # config, seguridad, deps
│   │   ├── models/     # SQLAlchemy
│   │   ├── schemas/    # Pydantic
│   │   └── services/
│   └── alembic/        # migraciones
├── worker/             # ETL multi-tenant (comparte models con backend vía paquete común)
├── frontend/           # React + TS + Vite
├── infra/              # docker-compose dev, Dockerfiles, IaC opcional
└── docs/
```

### Backend
- **Python 3.12, FastAPI, SQLAlchemy 2.x (async) + asyncpg, Alembic** para migraciones.
- **Auth:** JWT (access 15 min + refresh 7 días), hashing **argon2**. Middleware que inyecta
  `tenant_id` desde el token en TODAS las queries (scoping obligatorio, ver §8 seguridad).
- **S3:** boto3; media servida con **URLs prefirmadas de TTL corto (≤5 min)**, nunca bucket público.
- Tests: pytest + httpx; factories para datos multi-tenant.

### Worker ETL
- Mismo lenguaje/modelos que el backend (paquete compartido `core`/`models`).
- Scheduler: **APScheduler** en proceso worker propio (suficiente para decenas de tenants;
  no introducir Celery/colas en v1).
- Por tenant: credenciales Botmaker **cifradas en DB** (Fernet con clave en env/KMS),
  frecuencia configurable (cron simple: diario/quincenal + hora).
- Registra cada corrida en `etl_runs` (inicio, fin, etapa, filas, errores) para el monitoreo.

### Frontend
- **React 18 + TypeScript + Vite**, **Tailwind CSS**, **TanStack Query**, **React Router**,
  **Recharts** para gráficos. Componentes propios, sin librería de UI pesada.
- Idioma: español (sin i18n framework en v1; strings centralizados para facilitar futuro).

### Infra
- **Dev local:** `docker-compose` con `postgres:16`, `minio` (S3-compatible), backend,
  worker y frontend (Vite dev). Seed automático con datos de prueba.
- **Producción AWS (v1 pragmático):** 1 EC2 con docker-compose (backend+worker+nginx) +
  **RDS PostgreSQL** + **S3** + HTTPS con certificado (ALB+ACM o Caddy/LetsEncrypt).
  Documentar camino futuro a ECS Fargate. No sobre-ingenierizar v1.

## 5. Modelo de datos (PostgreSQL)

### 5.1 Port del esquema legacy (mapeo de tipos)

Portar las 18 tablas de `script creacion esquema KoalaETL.sql` con estas conversiones:
`NVARCHAR(n)`→`VARCHAR(n)`/`TEXT`, `NVARCHAR(MAX)`→`TEXT`, `DATETIME2`→`TIMESTAMPTZ`
(todo en UTC), `BIT`→`BOOLEAN`, `INT IDENTITY`→`BIGINT GENERATED ALWAYS AS IDENTITY`,
`MERGE`→`INSERT … ON CONFLICT … DO UPDATE`.

Tablas: `tenants, agents, queues, agent_performance_queues, agent_performance, agent_metrics,
chats, chat_details, chat_variables, chat_tags, messages, message_content, message_buttons,
message_carouselitems, message_media, message_location, message_call, encryption_params,
message_files`. Mantener PKs compuestas con `tenant_id` y FKs como están.

Cambios sobre el legacy:
- `message_files`: incluir desde el inicio `status` con CHECK
  (`ok/forbidden/not_found/error/skipped`), `file_path`→**`s3_key`** (nullable),
  agregar `size_bytes`, `content_type`. Índice `(tenant_id, status, file_type)`.
- Las columnas calculadas "_arg" del legacy NO se portan: las fechas se guardan UTC y la
  conversión a `America/Argentina/Buenos_Aires` se hace en queries (`AT TIME ZONE`) o en el front.
- Crear la vista **`vw_chat_full_conversation`** (el .pbix la usa y no existe en el repo legacy;
  reconstruirla): une `messages` + `message_content` + `message_files` + datos de sesión, con
  columnas al menos: `tenant_id, chat_id, contact_id, session_id, session_creation_time,
  message_id, message_time, message_from, content_type, content_text, content_selected_button,
  whatsapp_template_name, file_type, file_status, s3_key`.

### 5.2 Tablas nuevas de plataforma

```
users(id, tenant_id NULL para superadmin, email UNIQUE, password_hash, full_name,
      role ENUM('superadmin','tenant_admin','viewer'), is_active, created_at, last_login_at)
tenant_settings(tenant_id PK→tenants, botmaker_client_id, botmaker_secret_id,
      botmaker_token_enc, botmaker_refresh_token_enc, etl_schedule_cron,
      etl_initial_ts, etl_window_days, is_etl_enabled, logo_url NULL)
etl_control(tenant_id, endpoint, last_ts, PK(tenant_id, endpoint))   -- ahora POR TENANT
etl_runs(id, tenant_id, started_at, finished_at, status ENUM('running','ok','partial','failed'),
      stats JSONB, error_summary TEXT)
etl_stage_errors(id, run_id→etl_runs, stage, payload JSONB, created_at)
backup_jobs(id, tenant_id, requested_by→users, type ENUM('full','incremental'),
      status ENUM('pending','running','done','failed'), s3_key_result, size_bytes,
      created_at, finished_at, expires_at)
audit_log(id, tenant_id, user_id, action, entity, entity_id, detail JSONB, created_at)
```

**Importante:** el `etl_control` legacy era global (un solo tenant); ahora es por tenant.

### 5.3 Layout de S3

```
s3://<bucket>/
  tenants/{tenant_id}/files/{message_id}/{file_type}/{filename}
  tenants/{tenant_id}/backups/{backup_job_id}.zip
```

## 6. Worker ETL multi-tenant (refactor del legacy)

Portar la lógica de `etl_botmaker_logs.py` con esta estructura:

1. **Loop por tenant activo** (`tenant_settings.is_etl_enabled`), según su cron.
2. **Etapas por tenant, en orden, aisladas** (si una falla, loguear en `etl_stage_errors`
   y continuar — igual que el `_run_stage` legacy):
   `agent_performance` → `agent_metrics` (open+closed) → `messages` + subtablas →
   `chat_details` + variables + tags.
3. **Ventana deslizante por (tenant, endpoint)** con `etl_control`: `from = last_ts` (o
   `etl_initial_ts` la primera vez), `to = min(from + window_days, now)`. Actualizar `last_ts`
   al cerrar la etapa OK.
4. **Cliente HTTP Botmaker por tenant**: throttle ≥1.2 s entre requests, backoff en 429/5xx
   respetando `Retry-After`, refresh en 401 (persistiendo el refresh token rotado, cifrado).
5. **Descarga de archivos** (media/audio): intento directo → si 403, pedir temp-link →
   subir a S3 (`put_object` streaming) → upsert en `message_files` con `status` y `s3_key`
   (o `status` de fallo y `s3_key NULL`). Nunca frenar la etapa por un archivo.
6. **Upserts idempotentes** con `ON CONFLICT` (reemplazan los MERGE/IF NOT EXISTS legacy).
7. Registrar todo en `etl_runs` (filas por etapa en `stats` JSONB).
8. **Job de reintento de fallidas**: función reutilizable (la usa también la API §7.4) que toma
   filas de `message_files` con status en (`forbidden`,`not_found`,`error`) y reintenta el
   pipeline de descarga. Equivale a `etl_retry_message_files.py`.

## 7. API y Frontend por módulo

Convención API: prefijo `/api/v1`, todo scoped por tenant del token (superadmin puede pasar
`?tenant_id=` explícito). Paginación `?page/page_size`, fechas ISO UTC.

### 7.0 Auth y administración
- `POST /auth/login`, `POST /auth/refresh`, `GET /auth/me`.
- Superadmin: CRUD `/tenants`, `/tenants/{id}/settings` (credenciales Botmaker — write-only,
  nunca se devuelven), `/tenants/{id}/users`, `GET /etl/runs?tenant_id=`.
- Tenant admin: CRUD usuarios de su tenant (`viewer`/`tenant_admin`).
- Front: página Login; sección Administración (lista usuarios, alta/baja); para superadmin:
  gestión de tenants + estado del ETL por tenant (últimas corridas, errores).

### 7.1 Dashboards (espec extraída del .pbix real del cliente)

El .pbix tiene 6 páginas; replicar como 4 vistas con filtros globales
(**rango de fechas** y según vista **agente** o **contacto**):

**Página "Usuarios" (agentes)** — fuente `agent_metrics`:
- KPIs: total sesiones, clientes únicos (`chatId` distintos), promedio min hasta primera
  respuesta (`fromOpAssignedToOpFirstResponse`, promedio **sin ceros**, en minutos), % sesiones sin agente.
- Sesiones por año/mes (columnas, serie por agente).
- Sesiones por agente (torta/donut).
- Clientes por año/mes por agente (columnas) y clientes por agente (torta).
- Promedio min asignación→1ª respuesta por agente (barras).

**Página "Clientes"** — fuente `vw_chat_full_conversation`:
- Total sesiones por año/mes; sesiones iniciadas por externo; templates enviados
  (mensajes con `whatsapp_template_name` no nulo); sesiones sin intervención de agente.
- Segmentador: sesiones por `content_selected_button` (barras horizontales).
- Rankings por contacto: sesiones, mensajes, iniciadas por externo, templates (barras).

**Página "Conversaciones"** → es el Visor (§7.2).

**Página "Siniestros"** — mismos datos filtrados por la cola/flujo de siniestros:
- Sesiones diarias y mensuales; clientes diarios y mensuales; templates por día/mes
  (serie por texto del template); botones del flujo de siniestros; ranking de contactos frecuentes.
- La condición "es siniestro" debe ser **configurable por tenant** (nombre de cola o botón),
  no hardcodeada.

Endpoints sugeridos: `GET /metrics/summary`, `/metrics/sessions-by-month`,
`/metrics/sessions-by-agent`, `/metrics/clients-by-month`, `/metrics/first-response-by-agent`,
`/metrics/templates-by-month`, `/metrics/button-segmentation`, `/metrics/contact-rankings`,
todos con `?from&to&agent_id&queue&context=general|siniestros`.

### 7.2 Visor de conversaciones (diferencial del producto)

Hoy el cliente explora chats en una tabla plana de Power BI. El visor lo reemplaza:

- **Lista de chats** (izquierda): búsqueda por teléfono/nombre, orden por último mensaje,
  badge de tags. `GET /chats?search=&from=&to=`.
- **Timeline** (derecha): burbujas por emisor (`user` / `bot` / `agent` con nombre del agente),
  separadores por fecha y por **sesión** (`session_id`, cola), chips de botones del bot y
  botón seleccionado, templates marcados. `GET /chats/{chat_id}/messages?from=&to=`
  (paginado hacia atrás, estilo chat).
- **Media inline:** imágenes (thumbnail + lightbox), audio con reproductor HTML5, documentos
  descargables. El front pide `GET /files/{tenant}/{message_id}/{file_type}/url` → la API
  valida pertenencia al tenant y devuelve **URL prefirmada S3 (TTL ≤5 min)**.
- Archivos con `status != ok`: mostrar aviso "no descargado (status)" con acción **reintentar**
  (→ §7.4) visible según rol.
- Vista detalle del contacto: datos de `chat_details` (nombre, póliza vía `chat_variables`,
  tags, fechas).

### 7.3 Gestión de descargas fallidas
- `GET /files/failed?status=&file_type=&from=&to=` (tabla con paginado, conteos por status).
- `POST /files/retry` (lote con filtros o ids) → encola el job de reintento del worker;
  `GET /files/retry-jobs/{id}` para estado. Resultado visible: contadores antes/después.
- Front: página con resumen por status/tipo (cards), tabla y acción de reintento masivo.
  Visible para `tenant_admin` y superadmin.

### 7.4 Backup / exportación al servidor del cliente
v1 = **paquete de exportación descargable** (no replicación en vivo):
- `POST /backups` (tenant_admin) → job asíncrono en el worker que genera un ZIP en S3:
  - datos del tenant: un CSV (o NDJSON) por tabla, solo filas del tenant;
  - archivos: estructura `files/{message_id}/{file_type}/{filename}` desde S3;
  - `manifest.json` (fecha, conteos por tabla, versión del esquema) y un README de restauración.
- `GET /backups` (historial), `GET /backups/{id}/download` → URL prefirmada (TTL corto,
  `expires_at` en el job; los ZIP viejos se purgan con lifecycle de S3).
- Incremental (`type='incremental'`): solo filas/archivos nuevos desde el último backup `done`.
- Auditar toda descarga en `audit_log`.
- (Futuro, fuera de v1: agente instalable en el server del cliente que sincroniza
  automáticamente; dejar el diseño del paquete compatible con esa idea.)

## 8. Seguridad (requisitos duros)

1. **Scoping multi-tenant infalible:** ninguna query sin filtro `tenant_id`; resolver el tenant
   SIEMPRE desde el JWT (no de parámetros del cliente, salvo superadmin explícito). Tests
   automáticos de fuga cross-tenant (usuario A no puede ver chats/archivos/métricas de B,
   incluso adivinando ids).
2. Credenciales Botmaker **cifradas at-rest** (Fernet; clave fuera de la DB). Write-only en la API.
3. URLs de archivos: solo prefirmadas con TTL corto, generadas tras validar tenant + permisos.
4. Contraseñas: argon2; rate-limit en `/auth/login`; bloqueo tras N intentos.
5. `audit_log` para: logins, visualización de conversaciones, descargas de archivos y backups.
6. HTTPS obligatorio en producción; CORS restringido al dominio del portal.
7. Datos sensibles (es info de asegurados): no loguear contenido de mensajes en logs de app.

## 9. Fases de implementación

| Fase | Entregable | Criterio de aceptación |
|---|---|---|
| 0 | Scaffolding monorepo + docker-compose (postgres, minio, backend, worker, frontend) + CI lint/test | `docker compose up` levanta todo; healthcheck OK |
| 1 | Esquema Postgres completo (Alembic) + seed de datos de prueba multi-tenant (portar `datos_prueba_volumen.sql`, generar 2 tenants para probar aislamiento) | Migraciones reproducibles; seed crea 2 tenants con ~300 chats c/u |
| 2 | Auth + multi-tenancy + administración (tenants, users, settings) | Tests de scoping cross-tenant en verde |
| 3 | Worker ETL multi-tenant + `etl_runs` + reintento de fallidas (sin UI aún). Probar contra Botmaker real si hay credenciales; si no, contra mock HTTP con fixtures | Una corrida completa por tenant queda registrada con stats; archivos en MinIO |
| 4 | API de métricas + chats + archivos (presigned) | Endpoints devuelven los números del seed correctamente |
| 5 | Frontend: login, layout, dashboards (Usuarios/Clientes/Siniestros) | Vistas replican los gráficos del .pbix con filtros de fecha/agente |
| 6 | Frontend: visor de conversaciones con media | Se navega un chat completo con imágenes/audios reproducibles |
| 7 | Gestión de descargas fallidas (UI + jobs) | Reintento masivo cambia statuses y se refleja en UI |
| 8 | Módulo de backup/exportación | ZIP descargable restaurable según README incluido |
| 9 | Hardening + deploy AWS (EC2+RDS+S3, HTTPS) + runbook de operación | Checklist de seguridad §8 completo; deploy documentado |

Trabajar fase por fase; cada fase con sus tests antes de avanzar.

## 10. Variables de entorno (mínimas)

```
DATABASE_URL=postgresql+asyncpg://...
S3_ENDPOINT_URL=            # vacío en AWS real; http://minio:9000 en dev
S3_BUCKET=
S3_ACCESS_KEY= / S3_SECRET_KEY=
JWT_SECRET= / JWT_ACCESS_TTL=900 / JWT_REFRESH_TTL=604800
CREDENTIALS_ENCRYPTION_KEY=   # Fernet, para credenciales Botmaker
APP_BASE_URL=
ETL_DEFAULT_WINDOW_DAYS=30
LOG_LEVEL=INFO
```

## 11. Trampas conocidas (aprendidas del legacy — evitarlas)

1. El refresh token de Botmaker **rota** en cada refresh: persistir el nuevo inmediatamente
   o el tenant queda deslogueado para siempre.
2. Ventanas de más de ~1 mes contra Botmaker devuelven 400: respetar `window_days`.
3. El CDN de Botmaker a veces responde **200 con JSON** `{"message":"No file found"}` en vez
   de 404: detectar por `Content-Type` y contenido (status `not_found`).
4. Para media privada (403), el temp-link puede requerir la URL alternativa
   `https://storage.botmaker.com/<path>` en lugar de `storage.googleapis.com/...` (ver
   `_alt_file_url` en el legacy).
5. `agent_metrics` debe consultarse dos veces (`session-status=open` y `closed`).
6. Sesiones abiertas tienen métricas NULL: los promedios deben excluir NULL **y ceros**
   (el .pbix usa "promedio sin ceros").
7. Los teléfonos son los `chatId`/`contactId`: tratarlos como dato personal (no loguear).
8. Fechas siempre en UTC en DB; conversión a hora argentina solo en presentación.

## 12. Fuera de alcance v1 (no construir ahora)

- Agente de sincronización instalable en el server del cliente (el backup v1 es descarga manual).
- White-label completo por tenant (solo nombre/logo en header).
- i18n multi-idioma; notificaciones por email; SSO/Active Directory.
- Migración de datos históricos del cliente legacy (se planifica aparte; el seed simula datos).
