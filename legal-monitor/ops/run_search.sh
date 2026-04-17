#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "$ROOT_DIR/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
SCRIPT="$ROOT_DIR/scripts/run_search.py"
ENV_FILE=""

for candidate in "$ROOT_DIR/.env" "$WORKSPACE_ROOT/.env"; do
  if [[ -f "$candidate" ]]; then
    ENV_FILE="$candidate"
    break
  fi
done

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: no se encontró la virtualenv en $PYTHON_BIN" >&2
  echo "Crea la virtualenv e instala dependencias antes de correr el pipeline." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" ]]; then
  echo "Error: no se encontró el script en $SCRIPT" >&2
  exit 1
fi

if [[ -n "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "Error: DATABASE_URL no está definido. Revisa el .env del workspace antes de correr el pipeline." >&2
  exit 1
fi

(
  cd "$ROOT_DIR"
  PYTHONPATH="$ROOT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" - <<'PY'
from db import get_connection
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute('select 1')
        cur.fetchone()
print('DB preflight OK')
PY
)

exec "$PYTHON_BIN" "$SCRIPT" "$@"
