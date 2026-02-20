#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env.local ]]; then
  echo "Missing .env.local in $ROOT_DIR"
  echo "Create it from the template values first."
  exit 1
fi

while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
  if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
    key="${BASH_REMATCH[1]}"
    value="${BASH_REMATCH[2]}"
    if [[ -z "${!key+x}" ]]; then
      export "$key=$value"
    fi
  fi
done < .env.local

: "${HOST:=0.0.0.0}"
: "${PORT:=8000}"
: "${RELOAD:=true}"

echo "Starting Oscars app: HOST=${HOST} PORT=${PORT} RELOAD=${RELOAD} OSCARS_RESET_BALLOT_ON_START=${OSCARS_RESET_BALLOT_ON_START:-false}"

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
