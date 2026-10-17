#!/bin/sh
set -e

echo "[entrypoint] applying database migrations (alembic upgrade head)"
if ! python -m alembic upgrade head; then
    echo "[entrypoint] FATAL: migration failed (see alembic error above); not starting the server" >&2
    exit 1
fi
echo "[entrypoint] migrations OK; starting API on port ${PORT:-8000}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
