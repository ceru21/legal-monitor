"""
draft_emails.py — Crea borradores de Gmail para registros con email enriquecido.

Usa `gog gmail drafts create` vía subprocess con body por stdin para evitar
límites de shell. Mantiene un log acumulativo de pares (email, radicado) ya
procesados para prevenir duplicados entre runs.

Filtros disponibles (--draft-filter):
  all_with_email     — todos los registros que tengan emails_encontrados (default)
  accepted_and_review — solo decision in {accepted, review}
  accepted_only       — solo decision == accepted
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils import write_json

PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_TEMPLATE = PROJECT_ROOT / "config" / "email_template.html.jinja2"
DEFAULT_DRAFT_LOG = PROJECT_ROOT / "data" / "draft_log.jsonl"
DRAFT_LOG_MAX_AGE_DAYS = 30
RATE_LIMIT_SLEEP_S = 0.15  # 150ms entre drafts — dentro de cuota Gmail API

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def render_template(template_path: Path, variables: dict[str, Any]) -> str:
    """
    Renderiza el template Jinja2. Si Jinja2 no está instalado, usa str.replace
    como fallback básico (solo variables {{ key }}).
    """
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            autoescape=select_autoescape(["html"]),
        )
        tmpl = env.get_template(template_path.name)
        return tmpl.render(**variables)
    except ImportError:
        logger.warning("jinja2 no instalado; usando renderizado básico (sin filtros ni defaults)")
        raw = template_path.read_text(encoding="utf-8")
        for key, val in variables.items():
            raw = raw.replace("{{ " + key + " }}", str(val) if val else "")
        return raw


# ---------------------------------------------------------------------------
# Draft log — deduplicación persistente entre runs
# ---------------------------------------------------------------------------

def load_draft_log(log_path: Path) -> dict[tuple[str, str], str]:
    """
    Carga el log de drafts creados. Descarta entradas más viejas que
    DRAFT_LOG_MAX_AGE_DAYS para evitar crecimiento indefinido.
    Retorna dict: (email, radicado) -> draft_id
    """
    index: dict[tuple[str, str], str] = {}
    if not log_path.exists():
        return index
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=DRAFT_LOG_MAX_AGE_DAYS)
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry.get("created_at", "1970-01-01T00:00:00+00:00"))
            if ts < cutoff:
                continue
            key = (entry["email"], entry["radicado"])
            index[key] = entry["draft_id"]
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
    return index


def append_draft_log(log_path: Path, email: str, radicado: str, draft_id: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "email": email,
        "radicado": radicado,
        "draft_id": draft_id,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# gog subprocess
# ---------------------------------------------------------------------------

def gog_create_draft(
    to: str,
    subject: str,
    body_html: str,
    account: str | None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Llama a `gog gmail drafts create` pasando el body HTML por stdin vía
    archivo temporal (evita límite de longitud de argumentos de shell).
    Retorna dict con claves: ok, draft_id, error.
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", encoding="utf-8", delete=False) as f:
        f.write(body_html)
        body_file = f.name

    try:
        import os
        env = {**os.environ, "GOG_KEYRING_PASSWORD": os.environ.get("GOG_KEYRING_PASSWORD", "")}
        cmd = ["gog", "gmail", "drafts", "create",
               "--to", to,
               "--subject", subject,
               "--body-file", body_file,
               "--json"]
        if account:
            cmd += ["--account", account]
        if dry_run:
            cmd.append("--dry-run")

        logger.debug("gog cmd: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        if result.returncode != 0:
            return {"ok": False, "draft_id": None, "error": result.stderr.strip() or result.stdout.strip()}

        try:
            payload = json.loads(result.stdout)
            # gog --json devuelve envelope; el draft id puede estar en result.id o directamente
            draft_id = (
                payload.get("result", {}).get("id")
                or payload.get("id")
                or payload.get("draftId")
                or "unknown"
            )
            return {"ok": True, "draft_id": str(draft_id), "error": None}
        except json.JSONDecodeError:
            # dry-run o output no-JSON
            return {"ok": True, "draft_id": "dry-run", "error": None}

    except subprocess.TimeoutExpired:
        return {"ok": False, "draft_id": None, "error": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "draft_id": None, "error": "gog not found in PATH"}
    finally:
        Path(body_file).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Filtro de registros
# ---------------------------------------------------------------------------

FILTER_MODES = {"all_with_email", "accepted_and_review", "accepted_only"}


def should_draft(record: dict[str, Any], filter_mode: str) -> tuple[bool, str]:
    """
    Retorna (True, "") si se debe crear draft, o (False, razón) si no.
    """
    emails = record.get("emails_encontrados") or []
    if not emails:
        return False, "no_email"

    radicado = record.get("radicado_normalizado") or record.get("radicado_raw")
    demandado = record.get("demandado")
    if not radicado or not demandado:
        return False, "missing_fields:radicado_or_demandado"

    decision = record.get("decision")
    if filter_mode == "accepted_only" and decision != "accepted":
        return False, f"filter_rejected:decision={decision}"
    if filter_mode == "accepted_and_review" and decision not in {"accepted", "review"}:
        return False, f"filter_rejected:decision={decision}"

    return True, ""


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def create_drafts(
    records: list[dict[str, Any]],
    template_path: Path,
    gog_account: str | None,
    draft_log_path: Path,
    filter_mode: str,
    firma_vars: dict[str, str],
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """
    Itera los registros, crea un draft por par (email, radicado) único,
    y retorna la lista de registros con campos `draft_id`, `draft_status`,
    `draft_email_to` añadidos.
    """
    log_index = load_draft_log(draft_log_path)
    results: list[dict[str, Any]] = []
    seen_this_run: set[tuple[str, str]] = set()

    for record in records:
        eligible, skip_reason = should_draft(record, filter_mode)
        if not eligible:
            results.append({**record, "draft_id": None, "draft_status": f"skipped:{skip_reason}", "draft_email_to": None})
            continue

        radicado = record.get("radicado_normalizado") or record.get("radicado_raw", "")
        demandado = record.get("demandado", "")
        emails = record.get("emails_encontrados", [])

        # Un draft por cada email único × radicado — si son múltiples emails de la misma empresa
        # se crea un draft por cada uno para que el abogado elija cuál enviar.
        draft_ids = []
        draft_emails = []
        draft_status = "created"

        for email in emails:
            key = (email, radicado)

            if key in log_index:
                logger.info("Dup skip (log): email=%s radicado=%s", email, radicado)
                draft_ids.append(log_index[key])
                draft_emails.append(email)
                draft_status = "skipped:already_drafted"
                continue

            if key in seen_this_run:
                logger.info("Dup skip (run): email=%s radicado=%s", email, radicado)
                continue

            # Renderizar template
            subject = f"Acompañamiento jurídico — {radicado} — {record.get('despacho', '')}"
            template_vars = {
                "demandado": demandado,
                "radicado": radicado,
                "tipo_proceso": record.get("tipo_proceso") or "proceso civil",
                "despacho": record.get("despacho") or "",
                "fecha_publicacion": record.get("fecha_publicacion") or "",
                **firma_vars,
            }
            body_html = render_template(template_path, template_vars)

            result = gog_create_draft(
                to=email,
                subject=subject,
                body_html=body_html,
                account=gog_account,
                dry_run=dry_run,
            )

            if result["ok"]:
                draft_id = result["draft_id"]
                draft_ids.append(draft_id)
                draft_emails.append(email)
                seen_this_run.add(key)
                if not dry_run and draft_id != "dry-run":
                    append_draft_log(draft_log_path, email, radicado, draft_id)
                logger.info("Draft created: id=%s to=%s radicado=%s", draft_id, email, radicado)
            else:
                logger.error("Draft failed: to=%s radicado=%s error=%s", email, radicado, result["error"])
                draft_status = f"error:{result['error']}"

            time.sleep(RATE_LIMIT_SLEEP_S)

        results.append({
            **record,
            "draft_id": ", ".join(draft_ids) if draft_ids else None,
            "draft_status": draft_status,
            "draft_email_to": ", ".join(draft_emails) if draft_emails else None,
        })

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli() -> None:
    parser = argparse.ArgumentParser(description="Crea borradores de Gmail para registros con email enriquecido")
    parser.add_argument("records_json", help="JSON con lista de registros enriquecidos")
    parser.add_argument("--out-json", required=True, help="Ruta de salida JSON con draft_id añadido")
    parser.add_argument("--gog-account", help="Cuenta Gmail autenticada en gog (ej: abogado@firma.com)")
    parser.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Ruta al template HTML Jinja2")
    parser.add_argument("--draft-log", default=str(DEFAULT_DRAFT_LOG), help="Ruta al log acumulativo de drafts")
    parser.add_argument(
        "--draft-filter",
        default="all_with_email",
        choices=list(FILTER_MODES),
        help="Modo de filtro: all_with_email | accepted_and_review | accepted_only",
    )
    parser.add_argument("--firma-nombre", default="[NOMBRE BUFETE]")
    parser.add_argument("--abogado-nombre", default="[NOMBRE DEL ABOGADO]")
    parser.add_argument("--abogado-telefono", default="")
    parser.add_argument("--abogado-email", default="")
    parser.add_argument("--dry-run", action="store_true", help="No crea drafts reales; simula el flujo")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    records = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
    firma_vars = {
        "firma_nombre": args.firma_nombre,
        "abogado_nombre": args.abogado_nombre,
        "abogado_telefono": args.abogado_telefono,
        "abogado_email": args.abogado_email,
    }

    enriched = create_drafts(
        records=records,
        template_path=Path(args.template),
        gog_account=args.gog_account,
        draft_log_path=Path(args.draft_log),
        filter_mode=args.draft_filter,
        firma_vars=firma_vars,
        dry_run=args.dry_run,
    )

    write_json(args.out_json, enriched)

    # Resumen
    total = len(enriched)
    created = sum(1 for r in enriched if (r.get("draft_status") or "") == "created")
    skipped = sum(1 for r in enriched if "skipped" in (r.get("draft_status") or ""))
    errors = sum(1 for r in enriched if "error" in (r.get("draft_status") or ""))
    no_email = sum(1 for r in enriched if (r.get("draft_status") or "") == "skipped:no_email")
    missing = sum(1 for r in enriched if "missing_fields" in (r.get("draft_status") or ""))

    print(json.dumps({
        "total_records": total,
        "drafts_created": created,
        "skipped_total": skipped,
        "skipped_no_email": no_email,
        "skipped_missing_fields": missing,
        "errors": errors,
        "out_json": args.out_json,
        "dry_run": args.dry_run,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
