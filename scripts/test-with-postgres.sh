#!/usr/bin/env bash
# Run pytest for the Python SDK against the running docker-compose Postgres and
# Valkey. Passes through any args to `pytest` (e.g. `tests/test_sessions.py`).
set -euo pipefail

cd "$(dirname "$0")/.."

PG_PASS="${POSTGRES_PASSWORD:-}"
VALKEY_PASS="${VALKEY_PASSWORD:-}"
for env_path in ../../.env ../../../omur-core/.env; do
  if [[ -f "$env_path" ]]; then
    if [[ -z "$PG_PASS" ]]; then
      PG_PASS="$(grep -E '^POSTGRES_PASSWORD=' "$env_path" | cut -d= -f2-)"
    fi
    if [[ -z "$VALKEY_PASS" ]]; then
      VALKEY_PASS="$(grep -E '^VALKEY_PASSWORD=' "$env_path" | cut -d= -f2-)"
    fi
  fi
done
if [[ -z "$PG_PASS" ]]; then
  echo "POSTGRES_PASSWORD not set and not found in ../../.env" >&2
  exit 1
fi

# The backend network is internal-only (no egress). Attach to egress first so
# pip can reach PyPI, then connect backend so Postgres/Valkey resolve.
NAME="omur-sdk-test-$$"
trap "docker rm -f $NAME >/dev/null 2>&1 || true" EXIT

docker create --name "$NAME" \
  --network omur-core_egress \
  --dns 8.8.8.8 \
  -v "$PWD":/app \
  -w /app \
  -e TEST_POSTGRES_DSN="postgres://omur:${PG_PASS}@postgres:5432/omur?sslmode=disable" \
  -e TEST_REDIS_ADDR="valkey:6379" \
  -e TEST_REDIS_PASSWORD="${VALKEY_PASS}" \
  python:3.13 \
  bash -c "pip install -q -e '.[dev]' httpx && pytest $*" >/dev/null

docker network connect omur-core_backend "$NAME"
docker start --attach "$NAME"
