#!/usr/bin/env bash
set -Eeo pipefail

echo "Waiting for PostgreSQL at ${POSTGRES_HOST:-localhost}:${POSTGRES_PORT:-5432}..."
until python -c "
import socket, sys
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('${POSTGRES_HOST:-localhost}', int('${POSTGRES_PORT:-5432}')))
    s.close()
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; do
  echo "PostgreSQL is unavailable - sleeping 1s"
  sleep 1
done
echo "PostgreSQL is up and accepting connections!"

# Run migrations if configured
if command -v alembic >/dev/null 2>&1 && [ -f alembic.ini ]; then
    echo "Running database migrations..."
    alembic upgrade head || echo "Migration skipped or completed"
fi

exec "$@"
