#!/usr/bin/env bash
# Levanta un cluster PostgreSQL local de desarrollo/tests sin root (initdb + pg_ctl).
# Uso: ./backend/scripts/dev_pg.sh start|stop|status
set -euo pipefail

PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
PGDATA="${KOALA_PGDATA:-$HOME/.koala-pgdata}"
PGPORT="${KOALA_PGPORT:-54330}"
PGSOCK="/tmp"

case "${1:-start}" in
  start)
    if [ ! -d "$PGDATA" ]; then
      "$PGBIN/initdb" -D "$PGDATA" -U koala --auth=trust -E UTF8 >/dev/null
    fi
    if ! "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
      "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGDATA/server.log" \
        -o "-p $PGPORT -k $PGSOCK -c listen_addresses=127.0.0.1" start >/dev/null
    fi
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U koala -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='koala'" | grep -q 1 || \
      "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U koala koala
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U koala -d postgres -tc \
      "SELECT 1 FROM pg_database WHERE datname='koala_test'" | grep -q 1 || \
      "$PGBIN/createdb" -h 127.0.0.1 -p "$PGPORT" -U koala koala_test
    echo "PostgreSQL dev listo en 127.0.0.1:$PGPORT (db: koala, koala_test)"
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGDATA" stop -m fast
    ;;
  status)
    "$PGBIN/pg_ctl" -D "$PGDATA" status
    ;;
  *)
    echo "Uso: $0 start|stop|status" >&2
    exit 1
    ;;
esac
