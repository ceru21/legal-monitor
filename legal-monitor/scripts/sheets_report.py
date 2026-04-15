"""
sheets_report.py — Módulo 7: Reporte de ejecución en Google Sheets.

Estrategia:
- Una carpeta en Drive por configuración (SHEETS_FOLDER_NAME)
- Un Spreadsheet por mes: "Legal Monitor YYYY-MM"
- Una pestaña por ejecución: "DD HH:MM run_label[:20]"
- Todos los registros sin filtrar, con headers en fila 1

Cada ejecución:
  1. Busca/crea la carpeta en Drive
  2. Busca/crea el Sheet del mes en esa carpeta
  3. Agrega una pestaña nueva con el label de la ejecución
  4. Escribe headers + datos
  5. Formatea headers (bold, freeze)

Restricción de seguridad: usa --enable-commands=sheets,drive en gog.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils import write_json

PROJECT_ROOT = SCRIPT_DIR.parent
SHEETS_FOLDER_NAME = "Legal Monitor — Ejecuciones"
RATE_LIMIT_S = 0.3

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# gog subprocess helper
# ---------------------------------------------------------------------------

def _gog(args: list[str], account: str) -> dict[str, Any]:
    """Ejecuta gog con restricción a sheets/drive y retorna el JSON parseado."""
    env = {**os.environ, "GOG_KEYRING_PASSWORD": os.environ.get("GOG_KEYRING_PASSWORD", "")}
    cmd = ["gog", "--enable-commands", "sheets,drive"] + args + ["--account", account, "--json"]
    logger.debug("gog: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"gog error: {result.stderr.strip() or result.stdout.strip()}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw": result.stdout.strip()}


def _gog_plain(args: list[str], account: str) -> str:
    """Ejecuta gog y retorna stdout crudo (para comandos sin --json)."""
    env = {**os.environ, "GOG_KEYRING_PASSWORD": os.environ.get("GOG_KEYRING_PASSWORD", "")}
    cmd = ["gog", "--enable-commands", "sheets,drive"] + args + ["--account", account]
    logger.debug("gog plain: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"gog error: {result.stderr.strip() or result.stdout.strip()}")
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Drive: carpeta
# ---------------------------------------------------------------------------

def get_or_create_folder(folder_name: str, account: str) -> str:
    """Retorna el ID de la carpeta, creándola si no existe."""
    data = _gog(["drive", "ls", "--query", f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder'", "--max", "5"], account)
    files = data.get("files") or data.get("result", {}).get("files", [])
    if files:
        folder_id = files[0].get("id")
        logger.info("Carpeta existente: %s (%s)", folder_name, folder_id)
        return folder_id

    data = _gog(["drive", "mkdir", folder_name], account)
    folder_id = (
        data.get("folder", {}).get("id")
        or data.get("id")
        or data.get("result", {}).get("id")
    )
    logger.info("Carpeta creada: %s (%s)", folder_name, folder_id)
    return folder_id


# ---------------------------------------------------------------------------
# Sheets: spreadsheet mensual
# ---------------------------------------------------------------------------

def get_or_create_monthly_sheet(folder_id: str, month_label: str, account: str) -> str:
    """
    Retorna el ID del spreadsheet del mes, creándolo si no existe.
    Busca en Drive dentro de la carpeta por nombre exacto.
    """
    title = f"Legal Monitor {month_label}"
    query = f"name='{title}' and '{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
    data = _gog(["drive", "ls", "--query", query, "--max", "5"], account)
    files = data.get("files") or data.get("result", {}).get("files", [])
    if files:
        sheet_id = files[0].get("id")
        logger.info("Sheet existente: %s (%s)", title, sheet_id)
        return sheet_id

    data = _gog(["sheets", "create", title, "--parent", folder_id, "--sheets", "tmp"], account)
    sheet_id = data.get("spreadsheetId") or data.get("result", {}).get("spreadsheetId")
    logger.info("Sheet creado: %s (%s)", title, sheet_id)
    time.sleep(RATE_LIMIT_S)
    return sheet_id


# ---------------------------------------------------------------------------
# Tab de ejecución
# ---------------------------------------------------------------------------

def make_tab_name(run_label: str, now: datetime) -> str:
    """Genera nombre de pestaña: 'DD HH:MM <sufijo>'"""
    prefix = now.strftime("%d %H:%M")
    # Tomar parte descriptiva del run_label (fecha final)
    parts = run_label.split("_")
    suffix = parts[-1][:8] if parts else run_label[:8]  # ej: 20260324
    return f"{prefix} {suffix}"


def ensure_tab(sheet_id: str, tab_name: str, account: str) -> str:
    """Agrega la pestaña; si ya existe con ese nombre le añade un sufijo."""
    try:
        _gog_plain(["sheets", "add-tab", sheet_id, tab_name], account)
        logger.info("Pestaña creada: %s", tab_name)
        time.sleep(RATE_LIMIT_S)
        return tab_name
    except RuntimeError as e:
        if "already exists" in str(e).lower():
            alt = f"{tab_name}b"
            _gog_plain(["sheets", "add-tab", sheet_id, alt], account)
            logger.info("Pestaña (alt): %s", alt)
            time.sleep(RATE_LIMIT_S)
            return alt
        raise


# ---------------------------------------------------------------------------
# Escritura de datos
# ---------------------------------------------------------------------------

REPORT_COLUMNS = [
    "despacho_id",
    "despacho",
    "fecha_publicacion",
    "titulo_publicacion",
    "radicado_normalizado",
    "tipo_proceso",
    "actuacion",
    "demandante",
    "demandado",
    "decision",
    "revision_manual",
    "match_total",
    "emails_encontrados",
    "email_db",
    "source_labels",
    "email_2023",
    "email_2025",
    "draft_status",
    "draft_email_to",
    "blacklisted",
    "blacklist_match",
]


def _cell_value(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _rows_to_gog_format(rows: list[list[str]]) -> str:
    """
    Convierte lista de filas al formato que acepta gog sheets append:
    filas separadas por coma, celdas separadas por pipe.
    Escapa pipes y comas dentro de los valores.
    """
    encoded_rows = []
    for row in rows:
        cells = [cell.replace("|", " ").replace(",", " ") for cell in row]
        encoded_rows.append("|".join(cells))
    return ",".join(encoded_rows)


def write_records_to_tab(
    sheet_id: str,
    tab_name: str,
    records: list[dict[str, Any]],
    account: str,
) -> int:
    """
    Escribe headers + datos en la pestaña fila por fila.
    gog sheets append usa formato: filas=coma, celdas=pipe.
    Batches de 50 filas para no exceder límite de argumentos de shell.
    """
    BATCH = 50
    range_ref = f"'{tab_name}'!A1"

    # Headers
    header_encoded = _rows_to_gog_format([REPORT_COLUMNS])
    _gog(["sheets", "append", sheet_id, range_ref, header_encoded], account)
    time.sleep(RATE_LIMIT_S)

    # Datos en batches
    rows_written = 0
    batch_rows = []
    for record in records:
        batch_rows.append([_cell_value(record.get(col)) for col in REPORT_COLUMNS])
        if len(batch_rows) >= BATCH:
            encoded = _rows_to_gog_format(batch_rows)
            _gog(["sheets", "append", sheet_id, range_ref, encoded], account)
            rows_written += len(batch_rows)
            batch_rows = []
            time.sleep(RATE_LIMIT_S)

    if batch_rows:
        encoded = _rows_to_gog_format(batch_rows)
        _gog(["sheets", "append", sheet_id, range_ref, encoded], account)
        rows_written += len(batch_rows)
        time.sleep(RATE_LIMIT_S)

    # Freeze fila de headers
    try:
        _gog_plain(["sheets", "freeze", sheet_id, "--sheet", tab_name, "--rows", "1"], account)
        time.sleep(RATE_LIMIT_S)
    except Exception:
        pass  # no crítico

    logger.info("Filas escritas: %d en pestaña '%s'", rows_written, tab_name)
    return rows_written


# ---------------------------------------------------------------------------
# Entry point principal
# ---------------------------------------------------------------------------

def export_to_sheets(
    run_label: str,
    records: list[dict[str, Any]],
    account: str,
    folder_name: str = SHEETS_FOLDER_NAME,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Orquesta todo el flujo: carpeta → sheet mensual → pestaña → datos.
    Retorna dict con sheet_id, tab_name, rows_written, sheet_url.
    """
    now = datetime.now(tz=timezone.utc)
    month_label = now.strftime("%Y-%m")
    tab_name = make_tab_name(run_label, now)

    if dry_run:
        logger.info("DRY RUN — no se escribirá nada en Sheets")
        return {
            "dry_run": True,
            "folder_name": folder_name,
            "sheet_title": f"Legal Monitor {month_label}",
            "tab_name": tab_name,
            "records": len(records),
        }

    folder_id = get_or_create_folder(folder_name, account)
    sheet_id = get_or_create_monthly_sheet(folder_id, month_label, account)
    tab_name = ensure_tab(sheet_id, tab_name, account)
    rows_written = write_records_to_tab(sheet_id, tab_name, records, account)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    return {
        "folder_id": folder_id,
        "sheet_id": sheet_id,
        "sheet_url": sheet_url,
        "tab_name": tab_name,
        "rows_written": rows_written,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    parser = argparse.ArgumentParser(description="Exporta registros de una ejecución a Google Sheets")
    parser.add_argument("records_json", help="JSON con lista de registros (run_payload.json o similar)")
    parser.add_argument("--run-label", required=True)
    parser.add_argument("--gog-account", required=True)
    parser.add_argument("--folder-name", default=SHEETS_FOLDER_NAME)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    payload = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
    # Soporta run_payload.json (con clave "records") o lista directa
    records = payload.get("records", payload) if isinstance(payload, dict) else payload

    result = export_to_sheets(
        run_label=args.run_label,
        records=records,
        account=args.gog_account,
        folder_name=args.folder_name,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
