#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
SCRIPT="$ROOT_DIR/scripts/run_search.py"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: no se encontró la virtualenv en $PYTHON_BIN" >&2
  echo "Crea la virtualenv e instala dependencias antes de correr el pipeline." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" ]]; then
  echo "Error: no se encontró el script en $SCRIPT" >&2
  exit 1
fi

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Error: DATABASE_URL no está definido. Revisa $ENV_FILE antes de correr el pipeline." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT" "$@"
