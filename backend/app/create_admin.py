"""Crea (o resetea la contraseña de) un superadmin. Para el bootstrap de producción.

Uso:
    python -m app.create_admin --email admin@vendor.com --name "Admin"
    (pide la contraseña por stdin; o pasarla con --password, menos seguro)
"""

import argparse
import getpass

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ROLE_SUPERADMIN, hash_password
from app.models import User


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", default=None)
    args = parser.parse_args()

    password = args.password or getpass.getpass("Contraseña del superadmin: ")
    if len(password) < 8:
        raise SystemExit("La contraseña debe tener al menos 8 caracteres")

    engine = create_engine(get_settings().database_url_sync)
    with Session(engine) as db:
        user = db.scalar(select(User).where(User.email == args.email.lower()))
        if user is None:
            db.add(User(
                tenant_id=None, email=args.email.lower(),
                password_hash=hash_password(password),
                full_name=args.name, role=ROLE_SUPERADMIN, is_active=True,
            ))
            print(f"Superadmin {args.email} creado.")
        else:
            user.password_hash = hash_password(password)
            user.is_active = True
            print(f"Contraseña de {args.email} actualizada.")
        db.commit()


if __name__ == "__main__":
    main()
