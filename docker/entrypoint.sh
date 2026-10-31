#!/usr/bin/env bash
# Waits for Postgres/Redis, then optionally migrates/seeds before exec'ing the command.
#   MIGRATE_ON_START=1   run `migrate` (default 1 for the api service)
#   SEED_ON_START=1      run `seed_catalog --demo` once (dev convenience)
set -euo pipefail

wait_for() {
  local name=$1 host=$2 port=$3 tries=60
  until (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; do
    tries=$((tries - 1))
    if [ "$tries" -le 0 ]; then echo "✗ ${name} at ${host}:${port} not reachable"; exit 1; fi
    echo "… waiting for ${name} (${host}:${port})"; sleep 1
  done
  echo "✓ ${name} is up"
}

if [ -n "${DATABASE_URL:-}" ]; then
  host=$(python - <<'PY'
import os, urllib.parse as u; p=u.urlparse(os.environ["DATABASE_URL"]); print(p.hostname or "db")
PY
)
  port=$(python - <<'PY'
import os, urllib.parse as u; p=u.urlparse(os.environ["DATABASE_URL"]); print(p.port or 5432)
PY
)
  wait_for postgres "$host" "$port"
fi
if [ -n "${REDIS_URL:-}" ]; then
  rhost=$(python - <<'PY'
import os, urllib.parse as u; p=u.urlparse(os.environ["REDIS_URL"]); print(p.hostname or "redis")
PY
)
  rport=$(python - <<'PY'
import os, urllib.parse as u; p=u.urlparse(os.environ["REDIS_URL"]); print(p.port or 6379)
PY
)
  wait_for redis "$rhost" "$rport"
fi

if [ "${MIGRATE_ON_START:-0}" = "1" ]; then
  python manage.py migrate --noinput
fi
if [ "${SEED_ON_START:-0}" = "1" ]; then
  python manage.py seed_catalog --demo
fi

exec "$@"
