#!/bin/bash
# gog_restricted.sh — Wrapper que restringe gog a solo crear borradores de Gmail.
#
# Uso: sustituir llamadas a `gog` por este script para garantizar que
# OpenClaw no pueda ejecutar ningún otro comando de la API de Google.
#
# Comandos permitidos: gmail drafts create
# Comandos bloqueados: send, drive, calendar, contacts, sheets, docs, etc.

set -euo pipefail

GOG_BIN="${GOG_BIN:-gog}"
GOG_KEYRING_PASSWORD="${GOG_KEYRING_PASSWORD:-}"

# Solo permite el subcomando: gmail drafts create
if [[ "${1:-}" != "gmail" ]] || [[ "${2:-}" != "drafts" ]] || [[ "${3:-}" != "create" ]]; then
  echo "ERROR: comando no permitido. Este wrapper solo permite: gmail drafts create" >&2
  exit 1
fi

export GOG_KEYRING_PASSWORD
exec "$GOG_BIN" --enable-commands="gmail" "$@"
