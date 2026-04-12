"""
deep_enrich.py — Módulo 9: Enriquecimiento profundo de empresas sin email.

Flujo:
  1. Toma registros con found_cc=True y sin email (passed matcher + en CC pero sin email)
  2. Por cada empresa: busca NIT + email en internet con scoring de confianza
  3. Escribe resultados en Sheet "Legal Monitor Pendientes YYYY-MM" para revisión
  4. El bufete revisa y solicita creación de drafts cuando esté listo

Uso CLI:
  python3 scripts/deep_enrich.py run_payload.json \
    --gog-account mdetech01@gmail.com \
    [--max 100] [--dry-run]

Crear drafts desde Sheet pendiente:
  python3 scripts/deep_enrich.py --create-drafts \
    --pending-sheet "Legal Monitor Pendientes 2026-03" \
    --pending-tab "28 13:00 20260328" \
    --gog-account mdetech01@gmail.com \
    --firma-nombre "Bufete" --abogado-nombre "Dr. X"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from blacklist import normalize as normalize_name
from internet_search import enrich_empresa
from sheets_report import get_or_create_folder, get_or_create_monthly_sheet, ensure_tab, RATE_LIMIT_S

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "deep_enrich.yaml"
DEFAULT_ENRICH_LOG = PROJECT_ROOT / "data" / "enrich_log.jsonl"

PENDING_COLUMNS = [
    "radicado_normalizado",
    "despacho",
    "fecha_publicacion",
    "tipo_proceso",
    "actuacion",
    "demandado",
    "nit",
    "email_encontrado",
    "telefono",
    "pagina_web",
    "fuente",
    "score",
    "confianza",
    "draft_creado",
]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        return {}


# ---------------------------------------------------------------------------
# Enrich log (deduplicación)
# ---------------------------------------------------------------------------

def load_enrich_log(path: Path, ttl_days: int = 30) -> dict[str, dict]:
    """Carga el log de empresas ya procesadas. Descarta entradas > TTL días."""
    index: dict[str, dict] = {}
    if not path.exists():
        return index
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=ttl_days)
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry.get("processed_at", "1970-01-01T00:00:00+00:00"))
            if ts < cutoff:
                continue
            index[entry["nombre_normalizado"]] = entry
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
    return index


def append_enrich_log(path: Path, nombre: str, result: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "nombre_normalizado": normalize_name(nombre),
        "nombre_original": nombre,
        "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        **result,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Filtrar registros elegibles
# ---------------------------------------------------------------------------

def filter_eligible(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Elegibles:
    - decision = accepted o review
    - found_cc = True (encontrado en CC pero sin email)
    - emails_encontrados vacío
    - blacklisted = False
    - demandado no es persona natural (heurística)
    """
    CORP_RE = re.compile(
        r'\b(sas|s\.a\.s|s\.a|ltda|limitada|s en c|e\.u|empresa|constructora|'
        r'inversiones|grupo|inmobiliaria|comercializadora|distribuidora|servicios|'
        r'ingenieria|soluciones|logistica|transporte|transportes|alimentos|'
        r'ferreteria|consultores|asociados|clinica|fundacion|cooperativa|'
        r'corporacion|compania|cia)\b',
        re.IGNORECASE,
    )

    eligible = []
    for r in records:
        if r.get("decision") not in ("accepted", "review"):
            continue
        if not r.get("found_cc"):
            continue
        if r.get("emails_encontrados"):
            continue
        if r.get("blacklisted"):
            continue
        demandado = r.get("demandado") or ""
        if not demandado.strip():
            continue
        # Solo personas jurídicas
        if not CORP_RE.search(demandado) and len(demandado.split()) < 4:
            continue
        eligible.append(r)
    return eligible


# ---------------------------------------------------------------------------
# Deduplicar por empresa (mismo demandado normalizado)
# ---------------------------------------------------------------------------

def dedup_by_empresa(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result = []
    for r in records:
        key = normalize_name(r.get("demandado", ""))
        if key not in seen:
            seen.add(key)
            result.append(r)
    return result


# ---------------------------------------------------------------------------
# Sheets — pendientes
# ---------------------------------------------------------------------------

def _gog_cmd(args: list[str], account: str) -> dict[str, Any]:
    env = {**os.environ, "GOG_KEYRING_PASSWORD": os.environ.get("GOG_KEYRING_PASSWORD", "")}
    cmd = ["gog", "--enable-commands", "sheets,drive"] + args + ["--account", account, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"gog error: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _rows_to_gog_format(rows: list[list[str]]) -> str:
    encoded = []
    for row in rows:
        cells = [str(c).replace("|", " ").replace(",", " ") for c in row]
        encoded.append("|".join(cells))
    return ",".join(encoded)


def write_pending_sheet(
    records: list[dict[str, Any]],
    enrich_results: dict[str, dict],
    run_label: str,
    account: str,
    folder_name: str,
    pending_prefix: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    month_label = now.strftime("%Y-%m")
    sheet_title = f"{pending_prefix} {month_label}"
    parts = run_label.split("_")
    tab_suffix = parts[-1][:8] if parts else run_label[:8]
    tab_name = f"{now.strftime('%d %H:%M')} {tab_suffix}"

    if dry_run:
        return {"dry_run": True, "sheet_title": sheet_title, "tab_name": tab_name, "rows": len(records)}

    folder_id = get_or_create_folder(folder_name, account)
    # Buscar sheet de pendientes (diferente al de resultados)
    query = f"name='{sheet_title}' and '{folder_id}' in parents and mimeType='application/vnd.google-apps.spreadsheet'"
    data = _gog_cmd(["drive", "ls", "--query", query, "--max", "5"], account)
    files = data.get("files") or []
    if files:
        sheet_id = files[0]["id"]
    else:
        data = _gog_cmd(["sheets", "create", sheet_title, "--parent", folder_id, "--sheets", "tmp"], account)
        sheet_id = data.get("spreadsheetId")
    time.sleep(RATE_LIMIT_S)

    tab_name = ensure_tab(sheet_id, tab_name, account)

    # Escribir headers
    range_ref = f"'{tab_name}'!A1"
    header_encoded = _rows_to_gog_format([PENDING_COLUMNS])
    _gog_cmd(["sheets", "append", sheet_id, range_ref, header_encoded], account)
    time.sleep(RATE_LIMIT_S)

    # Escribir filas
    rows_written = 0
    batch = []
    for record in records:
        nombre = record.get("demandado", "")
        key = normalize_name(nombre)
        er = enrich_results.get(key, {})
        row = [
            record.get("radicado_normalizado", ""),
            record.get("despacho", ""),
            record.get("fecha_publicacion", ""),
            record.get("tipo_proceso", ""),
            record.get("actuacion", ""),
            nombre,
            er.get("nit", ""),
            er.get("email", ""),
            er.get("telefono", ""),
            er.get("pagina_web", ""),
            er.get("fuente", ""),
            str(er.get("score", "")),
            er.get("confianza", ""),
            "No",  # draft_creado
        ]
        batch.append(row)
        if len(batch) >= 50:
            _gog_cmd(["sheets", "append", sheet_id, range_ref, _rows_to_gog_format(batch)], account)
            rows_written += len(batch)
            batch = []
            time.sleep(RATE_LIMIT_S)

    if batch:
        _gog_cmd(["sheets", "append", sheet_id, range_ref, _rows_to_gog_format(batch)], account)
        rows_written += len(batch)
        time.sleep(RATE_LIMIT_S)

    # Freeze headers
    try:
        env = {**os.environ, "GOG_KEYRING_PASSWORD": ""}
        subprocess.run(
            ["gog", "--enable-commands", "sheets", "sheets", "freeze", sheet_id,
             "--sheet", tab_name, "--rows", "1", "--account", account],
            capture_output=True, text=True, env=env, timeout=15
        )
    except Exception:
        pass

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
    return {"sheet_id": sheet_id, "sheet_url": sheet_url, "tab_name": tab_name, "rows_written": rows_written}


# ---------------------------------------------------------------------------
# Crear drafts desde Sheet pendiente
# ---------------------------------------------------------------------------

def create_drafts_from_pending_sheet(
    sheet_name: str,
    tab_name: str,
    gog_account: str,
    firma_vars: dict[str, str],
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Lee el Sheet de pendientes, crea drafts para filas con email y draft_creado=No,
    y actualiza la columna draft_creado=Si por radicado.
    """
    from draft_emails import render_template, gog_create_draft

    template_path = PROJECT_ROOT / "config" / "email_template.html.jinja2"

    # Buscar sheet por nombre
    env = {**os.environ, "GOG_KEYRING_PASSWORD": ""}
    query = f"name='{sheet_name}' and mimeType='application/vnd.google-apps.spreadsheet'"
    data = _gog_cmd(["drive", "ls", "--query", query, "--max", "3"], gog_account)
    files = data.get("files") or []
    if not files:
        raise RuntimeError(f"Sheet '{sheet_name}' no encontrado en Drive")
    sheet_id = files[0]["id"]

    # Leer datos
    data = _gog_cmd(["sheets", "get", sheet_id, f"'{tab_name}'!A1:Z500"], gog_account)
    rows = data.get("values") or data.get("result", {}).get("values", [])
    if not rows:
        return {"error": "Sheet vacío o pestaña no encontrada"}

    headers = rows[0]
    try:
        col_radicado = headers.index("radicado_normalizado")
        col_demandado = headers.index("demandado")
        col_email = headers.index("email_encontrado")
        col_despacho = headers.index("despacho")
        col_tipo = headers.index("tipo_proceso")
        col_fecha = headers.index("fecha_publicacion")
        col_draft = headers.index("draft_creado")
    except ValueError as e:
        raise RuntimeError(f"Columna no encontrada: {e}")

    created = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows[1:], start=2):
        draft_val = row[col_draft] if col_draft < len(row) else ""
        if draft_val.lower() == "si":
            skipped += 1
            continue

        email = row[col_email] if col_email < len(row) else ""
        if not email or "@" not in email:
            skipped += 1
            continue

        radicado = row[col_radicado] if col_radicado < len(row) else ""
        demandado = row[col_demandado] if col_demandado < len(row) else ""
        despacho = row[col_despacho] if col_despacho < len(row) else ""
        tipo = row[col_tipo] if col_tipo < len(row) else ""
        fecha = row[col_fecha] if col_fecha < len(row) else ""

        subject = f"Acompañamiento jurídico — {radicado} — {despacho}"
        html = render_template(template_path, {
            "demandado": demandado,
            "radicado": radicado,
            "tipo_proceso": tipo,
            "despacho": despacho,
            "fecha_publicacion": fecha,
            **firma_vars,
        })

        if not dry_run:
            result = gog_create_draft(to=email, subject=subject, body_html=html, account=gog_account)
            if result["ok"]:
                # Actualizar draft_creado = Si en el Sheet
                col_letter = chr(65 + col_draft)
                cell_ref = f"'{tab_name}'!{col_letter}{i}"
                _gog_cmd(["sheets", "update", sheet_id, cell_ref, "Si"], gog_account)
                created += 1
                logger.info("Draft creado: to=%s radicado=%s", email, radicado)
                time.sleep(0.15)
            else:
                errors += 1
                logger.error("Draft fallido: to=%s error=%s", email, result["error"])
        else:
            created += 1
            logger.info("DRY RUN draft: to=%s radicado=%s", email, radicado)

    return {
        "sheet_id": sheet_id,
        "tab_name": tab_name,
        "drafts_created": created,
        "skipped": skipped,
        "errors": errors,
        "dry_run": dry_run,
    }


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def run_deep_enrich(
    records: list[dict[str, Any]],
    gog_account: str,
    max_empresas: int = 100,
    dry_run: bool = False,
    config_path: Path = DEFAULT_CONFIG_PATH,
    log_path: Path = DEFAULT_ENRICH_LOG,
    run_label: str = "",
) -> dict[str, Any]:
    cfg = load_config(config_path)
    ttl_days = cfg.get("enrich_log_ttl_days", 30)
    throttle_search = cfg.get("throttle_search_s", 3)
    throttle_page = cfg.get("throttle_page_s", 2)
    score_minimo = cfg.get("score_minimo_aceptar", 70)
    score_alta = cfg.get("score_alta_confianza", 90)
    folder_name = cfg.get("sheets_folder_name", "Legal Monitor — Ejecuciones")
    pending_prefix = cfg.get("sheets_pending_prefix", "Legal Monitor Pendientes")

    # Filtrar elegibles
    eligible = filter_eligible(records)
    eligible = dedup_by_empresa(eligible)

    # Priorizar: accepted primero, luego review
    eligible.sort(key=lambda r: 0 if r.get("decision") == "accepted" else 1)
    eligible = eligible[:max_empresas]

    logger.info("Deep enrich: %d empresas elegibles (cap %d)", len(eligible), max_empresas)

    # Cargar log de ya procesados
    enrich_log = load_enrich_log(log_path, ttl_days=ttl_days)

    enrich_results: dict[str, dict] = {}
    stats = {"alta": 0, "media": 0, "nit_only": 0, "no_encontrado": 0, "cached": 0}

    for record in eligible:
        nombre = record.get("demandado", "").replace("\n", " ").strip()
        key = normalize_name(nombre)

        # Verificar si ya fue procesado
        if key in enrich_log:
            logger.info("Cached: %s", nombre)
            enrich_results[key] = enrich_log[key]
            stats["cached"] += 1
            continue

        if dry_run:
            enrich_results[key] = {
                "nit": "DRY-RUN",
                "email": None,
                "telefono": None,
                "pagina_web": None,
                "fuente": None,
                "score": 0,
                "confianza": "dry_run",
            }
            continue

        er = enrich_empresa(
            nombre=nombre,
            throttle_search=throttle_search,
            throttle_page=throttle_page,
            score_minimo=score_minimo,
            score_alta=score_alta,
            config=cfg,
        )

        result_dict = er.to_dict()
        enrich_results[key] = result_dict
        stats[er.confianza if er.confianza in stats else "no_encontrado"] += 1

        # Guardar en log
        append_enrich_log(log_path, nombre, result_dict)

    # Solo escribir en Sheet los que tienen confianza aceptable
    to_write = [
        r for r in eligible
        if enrich_results.get(normalize_name(r.get("demandado", "")), {}).get("confianza")
        in ("alta", "media", "nit_only")
    ]

    sheets_result: dict[str, Any] = {}
    if to_write and not dry_run:
        sheets_result = write_pending_sheet(
            records=to_write,
            enrich_results=enrich_results,
            run_label=run_label,
            account=gog_account,
            folder_name=folder_name,
            pending_prefix=pending_prefix,
        )
    elif dry_run:
        sheets_result = {"dry_run": True, "would_write": len(to_write)}

    return {
        "empresas_procesadas": len(eligible),
        "stats": stats,
        "sheet_pendientes": sheets_result,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    parser = argparse.ArgumentParser(description="Módulo 9 — Enriquecimiento profundo de empresas")
    sub = parser.add_subparsers(dest="cmd")

    # Subcomando: enriquecer
    p_enrich = sub.add_parser("enrich", help="Enriquecer registros sin email")
    p_enrich.add_argument("records_json", help="run_payload.json o records JSON")
    p_enrich.add_argument("--gog-account", required=True)
    p_enrich.add_argument("--max", type=int, default=100)
    p_enrich.add_argument("--dry-run", action="store_true")
    p_enrich.add_argument("--verbose", "-v", action="store_true")

    # Subcomando: crear drafts desde Sheet pendiente
    p_drafts = sub.add_parser("drafts", help="Crear drafts desde Sheet pendiente")
    p_drafts.add_argument("--pending-sheet", required=True, help="Nombre del Sheet (ej: 'Legal Monitor Pendientes 2026-03')")
    p_drafts.add_argument("--pending-tab", required=True, help="Nombre de la pestaña (ej: '28 13:00 20260328')")
    p_drafts.add_argument("--gog-account", required=True)
    p_drafts.add_argument("--firma-nombre", default="[NOMBRE BUFETE]")
    p_drafts.add_argument("--abogado-nombre", default="[NOMBRE DEL ABOGADO]")
    p_drafts.add_argument("--abogado-telefono", default="")
    p_drafts.add_argument("--abogado-email", default="")
    p_drafts.add_argument("--dry-run", action="store_true")
    p_drafts.add_argument("--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, 'verbose', False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if args.cmd == "enrich":
        payload = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
        records = payload.get("records", payload) if isinstance(payload, dict) else payload
        run_label = payload.get("run_label", "") if isinstance(payload, dict) else ""

        result = run_deep_enrich(
            records=records,
            gog_account=args.gog_account,
            max_empresas=args.max,
            dry_run=args.dry_run,
            run_label=run_label,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.cmd == "drafts":
        firma_vars = {
            "firma_nombre": args.firma_nombre,
            "abogado_nombre": args.abogado_nombre,
            "abogado_telefono": args.abogado_telefono,
            "abogado_email": args.abogado_email,
        }
        result = create_drafts_from_pending_sheet(
            sheet_name=args.pending_sheet,
            tab_name=args.pending_tab,
            gog_account=args.gog_account,
            firma_vars=firma_vars,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    cli()
