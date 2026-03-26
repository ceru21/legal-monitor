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

# Comandos permitidos explícitamente:
#   gmail drafts create         — Módulo 5: borradores
#   sheets create               — Módulo 7: crear spreadsheet
#   sheets add-tab              — Módulo 7: nueva pestaña
#   sheets append               — Módulo 7: escribir datos
#   sheets freeze               — Módulo 7: formatear headers
#   sheets metadata             — Módulo 7: verificar existencia
#   drive ls                    — Módulo 7: buscar carpeta/sheet
#   drive mkdir                 — Módulo 7: crear carpeta

ALLOWED=false

if [[ "${1:-}" == "gmail" ]] && [[ "${2:-}" == "drafts" ]] && [[ "${3:-}" == "create" ]]; then
  ALLOWED=true
fi

if [[ "${1:-}" == "sheets" ]] && [[ "${2:-}" =~ ^(create|add-tab|append|freeze|metadata)$ ]]; then
  ALLOWED=true
fi

if [[ "${1:-}" == "drive" ]] && [[ "${2:-}" =~ ^(ls|mkdir)$ ]]; then
  ALLOWED=true
fi

if [[ "$ALLOWED" != "true" ]]; then
  echo "ERROR: comando no permitido: $*" >&2
  echo "Comandos permitidos: gmail drafts create | sheets create/add-tab/append/freeze/metadata | drive ls/mkdir" >&2
  exit 1
fi

export GOG_KEYRING_PASSWORD
exec "$GOG_BIN" --enable-commands="gmail,sheets,drive" "$@"
