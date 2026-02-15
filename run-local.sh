#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env.local ]]; then
  echo "Missing .env.local in $ROOT_DIR"
  echo "Create it from the template values first."
  exit 1
fi

set -a
source .env.local
set +a

: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${RELOAD:=true}"

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  UVICORN_CMD=("$ROOT_DIR/.venv/bin/python" -m uvicorn app.main:app --host "$HOST" --port "$PORT")
else
  UVICORN_CMD=(uvicorn app.main:app --host "$HOST" --port "$PORT")
fi

if [[ "$RELOAD" == "true" ]]; then
  exec "${UVICORN_CMD[@]}" --reload
else
  exec "${UVICORN_CMD[@]}"
fi
