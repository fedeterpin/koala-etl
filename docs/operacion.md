# Runbook de operación

## Alta de un tenant nuevo

1. Superadmin en el portal: **Administración → Tenants → Nuevo** (o `POST /api/v1/tenants`).
2. Cargar settings del tenant (`PUT /api/v1/tenants/{id}/settings`):
   - Credenciales Botmaker del cliente: `botmaker_client_id`, `botmaker_secret_id`,
     `botmaker_token`, `botmaker_refresh_token` (write-only; quedan cifradas).
   - `etl_initial_ts`: desde cuándo traer histórico (ej. fecha de alta del bot).
   - `etl_window_days`: ≤ 31 (Botmaker rechaza ventanas mayores a ~1 mes).
   - `etl_schedule_cron`: ej. `0 3 * * *` (diario 03:00 UTC) o `0 3 1,15 * *` (quincenal).
   - `siniestros_queue` / `siniestros_button`: condición del dashboard Siniestros.
   - `is_etl_enabled: true` para activar.
3. Crear el usuario admin del cliente (**Administración → Usuarios**).
4. La primera corrida del ETL arranca en el próximo tick del cron. Para histórico largo,
   el ETL avanza `window_days` por corrida: programar cron frecuente (cada hora) hasta
   alcanzar el presente y luego bajar a diario.

## Monitoreo del ETL

- Portal: **Administración → Monitoreo ETL** (por tenant) o `GET /api/v1/etl/runs?tenant_id=`.
- Estados: `ok` | `partial` (alguna etapa falló; ver `etl_stage_errors`) | `failed`.
- `stats` JSONB por corrida: filas por etapa, archivos ok/fallidos, ventana usada.
- SQL útil:

```sql
SELECT tenant_id, status, started_at, finished_at - started_at AS duracion,
       stats->'messages'->>'rows' AS mensajes
FROM etl_runs ORDER BY started_at DESC LIMIT 20;

SELECT stage, payload, created_at FROM etl_stage_errors
WHERE run_id = :run_id ORDER BY created_at;
```

### Problemas frecuentes (heredados del legacy)

| Síntoma | Causa probable | Acción |
|---|---|---|
| 401 permanente en un tenant | Refresh token desincronizado (rotó y no se persistió, p.ej. por edición manual) | Pedir credenciales nuevas a Botmaker y recargarlas en settings |
| 400 en messages | Ventana > 1 mes | Bajar `etl_window_days` |
| Muchos `forbidden` | Media privada cuyo temp-link falla | Reintentar más tarde (la API alternativa `storage.botmaker.com` ya se intenta sola) |
| `not_found` masivo | Botmaker ya purgó esos archivos | Irrecuperable: documentar al cliente |

## Reintento de descargas fallidas

- Portal: **Descargas fallidas** → filtrar → "Reintentar". El worker procesa el job y
  muestra contadores antes/después.
- CLI equivalente: encolar por SQL `INSERT INTO retry_jobs (tenant_id, filters, status) VALUES ('X', '{"statuses":["forbidden","error"],"limit":500}', 'pending');`

## Backups / exportación al cliente

- El cliente (tenant_admin) los genera desde el portal (**Backups**). ZIP con CSV por
  tabla + archivos + manifest + README de restauración. Expiran (`expires_at`, 7 días)
  y el lifecycle de S3 los purga.
- `type=incremental`: solo filas/archivos nuevos desde el último backup `done`.
- Toda descarga queda en `audit_log` (`action='backup_downloaded'`).

## Auditoría

```sql
SELECT action, count(*) FROM audit_log
WHERE created_at > now() - interval '7 days' GROUP BY action;
```

Acciones registradas: `login_ok/login_failed`, `chat_viewed`, `file_url_generated`,
`backup_requested/backup_downloaded`, `retry_enqueued`, `tenant_*`, `user_*`.

## Rotación de claves

- `JWT_SECRET`: rotar invalida sesiones activas (los usuarios reloguean). Sin más impacto.
- `CREDENTIALS_ENCRYPTION_KEY`: NO rotar en frío — primero desencriptar y re-encriptar
  `tenant_settings.botmaker_*_enc` con la clave nueva (script ad-hoc), luego cambiar la env.
- Credenciales Botmaker de un tenant: recargar por settings (write-only).
