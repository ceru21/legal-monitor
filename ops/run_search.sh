#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
SCRIPT="$ROOT_DIR/scripts/run_search.py"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Error: no se encontró la virtualenv en $PYTHON_BIN" >&2
  echo "Crea la virtualenv e instala dependencias antes de correr el pipeline." >&2
  exit 1
fi

if [[ ! -f "$SCRIPT" ]]; then
  echo "Error: no se encontró el script en $SCRIPT" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT" "$@"
