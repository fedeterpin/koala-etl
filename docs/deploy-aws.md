# Deploy v1 en AWS (EC2 + RDS + S3)

Camino pragmático para v1 (PLAN-APP.md §4): una EC2 con docker-compose, RDS PostgreSQL
y S3. Sin sobre-ingeniería; al final se documenta la migración futura a ECS Fargate.

## 1. Recursos

| Recurso | Recomendación v1 |
|---|---|
| EC2 | t3.small (Ubuntu 24.04), Docker + plugin compose. SG: 80/443 abiertos, 22 restringido |
| RDS PostgreSQL 16 | db.t4g.micro, 20 GB gp3, backups automáticos 7 días, NO público (SG solo desde la EC2) |
| S3 | 1 bucket privado (`koala-files-prod`). Block Public Access ON |
| IAM | Rol de instancia EC2 con política mínima sobre el bucket (Get/Put/Delete/List) |

### Lifecycle del bucket (purga de backups viejos)

```json
{
  "Rules": [{
    "ID": "purgar-backups",
    "Filter": { "Prefix": "tenants/" },
    "Status": "Enabled",
    "Expiration": { "Days": 30 },
    "NoncurrentVersionExpiration": { "NoncurrentDays": 7 }
  }]
}
```

Aplicar solo al prefijo `tenants/*/backups/` si se prefiere granularidad (los ZIP de
backup expiran; los archivos de media NO deben expirar — usar dos reglas con prefijos
`tenants/` + tag o estructurar la regla por prefijo de backup por tenant).
**Importante:** la regla de arriba como está borraría también los media a los 30 días;
en producción usar el prefijo exacto de backups o un bucket separado para backups.

## 2. HTTPS

Opción simple (sin ALB): **Caddy** como reverse proxy con Let's Encrypt automático.
Ver `infra/docker-compose.prod.yml` + `infra/Caddyfile`. Apuntar el DNS del dominio a la
EC2 (IP elástica) antes del primer arranque.

Alternativa: ALB + ACM si se quiere terminar TLS fuera de la instancia.

## 3. Pasos

```bash
# En la EC2
sudo apt update && sudo apt install -y docker.io docker-compose-v2
git clone <repo> koala && cd koala

# Configurar entorno de producción
cp .env.example .env.prod
#   DATABASE_URL=postgresql+asyncpg://koala:<pass>@<rds-endpoint>:5432/koala
#   S3_ENDPOINT_URL=            ← VACÍO en AWS real
#   S3_BUCKET=koala-files-prod
#   S3_ACCESS_KEY/SECRET_KEY=   ← vacíos si se usa rol de instancia (recomendado)
#   JWT_SECRET=$(openssl rand -hex 32)
#   CREDENTIALS_ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
#   CORS_ORIGINS=https://portal.midominio.com
#   APP_BASE_URL=https://portal.midominio.com

# Migraciones y arranque
docker compose -f infra/docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head

# Crear el primer superadmin (no usar el seed en producción)
docker compose -f infra/docker-compose.prod.yml exec backend python -m app.create_admin \
  --email admin@vendor.com --name "Admin" 
```

## 4. Checklist de seguridad (§8 del plan)

- [ ] Scoping multi-tenant: cubierto por diseño + tests `test_tenancy.py` en CI.
- [ ] Credenciales Botmaker cifradas (Fernet); `CREDENTIALS_ENCRYPTION_KEY` SOLO en la
      EC2 (o en AWS Secrets Manager/KMS), nunca en el repo ni en la DB.
- [ ] URLs de archivos: solo prefirmadas, TTL ≤ 5 min (techo duro en `services/s3.py`).
- [ ] argon2 + rate-limit de login (5 intentos / 15 min por IP+email).
- [ ] `audit_log` activo: logins, visualización de chats, descargas de archivos y backups.
- [ ] HTTPS obligatorio (Caddy/ACM); CORS restringido al dominio del portal.
- [ ] Logs de aplicación sin contenido de mensajes ni teléfonos (revisión en code review;
      los loggers del worker solo registran ids).
- [ ] RDS sin acceso público; bucket S3 con Block Public Access.
- [ ] Backups RDS automáticos + snapshot manual antes de cada migración.

## 5. Actualizaciones

```bash
git pull
docker compose -f infra/docker-compose.prod.yml build
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f infra/docker-compose.prod.yml up -d
```

## 6. Camino futuro a ECS Fargate

Cuando crezca la cantidad de tenants:
1. Subir las imágenes a ECR (mismo Dockerfile).
2. Dos servicios ECS: `backend` (detrás de ALB+ACM) y `worker` (sin LB, desired=1).
3. Secretos a AWS Secrets Manager (incl. `CREDENTIALS_ENCRYPTION_KEY` vía KMS).
4. El worker ya es single-instance-safe (jobs con `FOR UPDATE SKIP LOCKED`); para
   escalar horizontalmente el ETL, particionar tenants por hash en N workers.
