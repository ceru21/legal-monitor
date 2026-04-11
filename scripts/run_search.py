from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from blacklist import BlacklistFilter
from draft_emails import create_drafts
from enrich_contacts import enrich_records_from_db
from sheets_report import export_to_sheets
from export_results import build_export_payload, write_export_bundle
from matcher import decide
from parse_pdf import parse_pdf
from scraper_portal import DetailDocument, PortalClient, Publication
from utils import normalize_text, write_json
from validators import sanitize_exception, validate_date, validate_despacho_id

logger = logging.getLogger("legal_monitor.run_search")

def _load_pipeline_defaults() -> dict[str, Any]:
    """Carga los defaults del pipeline desde pipeline.yaml."""
    try:
        import yaml
        cfg_path = PROJECT_ROOT / "config" / "pipeline.yaml"
        if cfg_path.exists():
            data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            return data.get("defaults", {})
    except Exception:
        pass
    return {}


_DEFAULTS = _load_pipeline_defaults()
REFERENCE_DESPACHOS = PROJECT_ROOT / "references" / "despachos_medellin_civil_circuito.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "runs"


def valid_date(s: str) -> str:
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Fecha invalida, use YYYY-MM-DD: {s!r}")
    return s


def sanitize_filename(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or "archivo"


def load_scope_despachos() -> list[dict[str, Any]]:
    return json.loads(REFERENCE_DESPACHOS.read_text(encoding="utf-8"))


def rank_document(doc: DetailDocument) -> tuple[int, int, int, str]:
    label_norm = normalize_text(doc.label)
    score = 0
    if label_norm.endswith(".pdf"):
        score += 100
    if any(token in label_norm for token in ["planilla", "estado", "estados"]):
        score += 80
    if any(token in label_norm for token in ["aviso tutela", "tutela", "oficio", "demanda", "solicitud", "auto"]):
        score -= 40
    return (-score, 0 if doc.is_primary_candidate else 1, len(doc.label), doc.label)


def choose_primary_document(documents: list[DetailDocument]) -> DetailDocument | None:
    pdf_docs = [doc for doc in documents if normalize_text(doc.label).endswith(".pdf")]
    if not pdf_docs:
        return None
    pdf_docs.sort(key=rank_document)
    return pdf_docs[0]


def merge_record_context(
    run_label: str,
    fecha_inicio: str,
    fecha_fin: str,
    despacho_id: str,
    publication: Publication,
    pdf_doc: DetailDocument,
    pdf_path: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    decision = decide(row).to_dict()
    return {
        "run_label": run_label,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "despacho_id": despacho_id,
        "despacho": publication.despacho,
        "publication_id": publication.publication_id,
        "fecha_publicacion": publication.fecha_publicacion,
        "titulo_publicacion": publication.titulo_publicacion,
        "publication_url": publication.publication_url,
        "pdf_label": pdf_doc.label,
        "pdf_url": pdf_doc.url,
        "pdf_path": str(pdf_path),
        **row,
        **decision,
    }


def run_pipeline(
    fecha_inicio: str,
    fecha_fin: str,
    despacho_ids: list[str] | None,
    output_root: Path,
    no_db: bool = False,
    draft_emails: bool = False,
    gog_account: str | None = None,
    draft_filter: str = "all_with_email",
    firma_vars: dict[str, str] | None = None,
    draft_dry_run: bool = False,
    sheets_report: bool = False,
    sheets_dry_run: bool = False,
    no_db: bool = False,
) -> dict[str, Any]:
    client = PortalClient()
    scope = load_scope_despachos()
    if despacho_ids:
        selected = [item for item in scope if item["id"] in set(despacho_ids)]
    else:
        selected = scope

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_label = f"medellin_civil_circuito_{fecha_inicio}_a_{fecha_fin}_{run_ts}"
    run_dir = output_root / run_label
    pdf_dir = run_dir / "pdfs"
    export_dir = run_dir / "exports"
    diagnostics_dir = run_dir / "diagnostics"

    publications_manifest: list[dict[str, Any]] = []
    selected_docs_manifest: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    publications_total = 0
    pdfs_total = 0

    logger.info("Iniciando corrida %s | %d despachos", run_label, len(selected))

    for despacho in selected:
        despacho_id = despacho["id"]
        try:
            logger.info("Despacho %s — buscando publicaciones", despacho_id)
            html_text = client.search_html(fecha_inicio, fecha_fin, id_despacho=despacho_id)
            publications = client.extract_publications(html_text)
            publications_total += len(publications)
            publications_manifest.extend({"despacho_id": despacho_id, **publication.to_dict()} for publication in publications)

            if not publications:
                logger.info("Despacho %s — sin publicaciones", despacho_id)
                diagnostics.append({"despacho_id": despacho_id, "despacho": despacho["nombre"], "status": "no_publications"})
                continue

            logger.info("Despacho %s — %d publicacion(es)", despacho_id, len(publications))

            for publication in publications:
                try:
                    documents = client.fetch_detail_documents(publication.publication_url)
                    pdf_doc = choose_primary_document(documents)
                    selected_docs_manifest.append(
                        {
                            "despacho_id": despacho_id,
                            "despacho": publication.despacho,
                            "publication_id": publication.publication_id,
                            "publication_url": publication.publication_url,
                            "documents": [doc.to_dict() for doc in documents],
                            "selected_pdf": pdf_doc.to_dict() if pdf_doc else None,
                        }
                    )
                    if not pdf_doc:
                        diagnostics.append(
                            {
                                "despacho_id": despacho_id,
                                "despacho": publication.despacho,
                                "publication_id": publication.publication_id,
                                "status": "no_primary_pdf",
                            }
                        )
                        continue

                    pdf_filename = sanitize_filename(f"{despacho_id}_{pdf_doc.label}")
                    if not pdf_filename.lower().endswith(".pdf"):
                        pdf_filename += ".pdf"
                    pdf_path = pdf_dir / pdf_filename
                    client.download_document(pdf_doc.url, pdf_path)
                    pdfs_total += 1
                    logger.info("PDF descargado: %s", pdf_filename)

                    parsed_rows = [row.to_dict() for row in parse_pdf(pdf_path)]
                    logger.info("PDF %s — %d filas extraidas", pdf_filename, len(parsed_rows))
                    diagnostics.append(
                        {
                            "despacho_id": despacho_id,
                            "despacho": publication.despacho,
                            "publication_id": publication.publication_id,
                            "status": "ok",
                            "pdf": pdf_filename,
                            "rows": len(parsed_rows),
                        }
                    )
                    for row in parsed_rows:
                        records.append(
                            merge_record_context(
                                run_label=run_label,
                                fecha_inicio=fecha_inicio,
                                fecha_fin=fecha_fin,
                                despacho_id=despacho_id,
                                publication=publication,
                                pdf_doc=pdf_doc,
                                pdf_path=pdf_path,
                                row=row,
                            )
                        )
                except Exception as exc:
                    logger.error("despacho=%s pub=%s: %s", despacho_id, publication.publication_id, exc)
                    diagnostics.append(
                        {
                            "despacho_id": despacho_id,
                            "despacho": publication.despacho,
                            "publication_id": publication.publication_id,
                            "status": "error",
                            "error": str(exc),
                        }
                    )

        except Exception as exc:
            logger.error("despacho=%s: %s", despacho_id, exc)
            diagnostics.append(
                {
                    "despacho_id": despacho_id,
                    "despacho": despacho.get("nombre"),
                    "status": "error",
                    "error": str(exc),
                }
            )

    logger.info("Corrida completada — %d publicaciones, %d PDFs, %d filas", publications_total, pdfs_total, len(records))

    enrichment_enabled = False
    if not no_db:
        try:
            from db import get_session
            from db.repository import save_run
            with get_session() as session:
                records = enrich_records_from_db(records, session)
                enrichment_enabled = True
                metadata_for_save = {
                    "fecha_inicio": fecha_inicio,
                    "fecha_fin": fecha_fin,
                    "despachos_total": len(selected),
                    "publications_total": publications_total,
                    "pdfs_total": pdfs_total,
                    "enrichment_enabled": True,
                }
                save_run(
                    run_label=run_label,
                    fecha_inicio=fecha_inicio,
                    fecha_fin=fecha_fin,
                    metadata=metadata_for_save,
                    records=records,
                    session=session,
                )
        except Exception as exc:
            logger.warning("DB enrichment/persistence failed: %s. Continuing without DB.", sanitize_exception(exc))

    # Blacklist — último filtro antes de drafts
    _blacklist_path = PROJECT_ROOT / "config" / "blacklist.yaml"
    bf = BlacklistFilter.from_yaml(_blacklist_path)
    records = bf.apply(records)
    blacklisted_count = sum(1 for r in records if r.get("blacklisted"))
    if blacklisted_count:
        logger.info("Blacklist: %d registros marcados como excluidos", blacklisted_count)

    if draft_emails:
        from pathlib import Path as _Path
        _template = PROJECT_ROOT / "config" / "email_template.html.jinja2"
        _draft_log = output_root / "draft_log.jsonl"
        records = create_drafts(
            records=records,
            template_path=_template,
            gog_account=gog_account,
            draft_log_path=_draft_log,
            filter_mode=draft_filter,
            firma_vars=firma_vars or {},
            dry_run=draft_dry_run,
        )

    # Blacklist — último filtro antes de drafts
    _blacklist_path = PROJECT_ROOT / "config" / "blacklist.yaml"
    bf = BlacklistFilter.from_yaml(_blacklist_path)
    records = bf.apply(records)
    blacklisted_count = sum(1 for r in records if r.get("blacklisted"))
    if blacklisted_count:
        logger.info("Blacklist: %d registros marcados como excluidos", blacklisted_count)

    if draft_emails:
        from pathlib import Path as _Path
        _template = PROJECT_ROOT / "config" / "email_template.html.jinja2"
        _draft_log = output_root / "draft_log.jsonl"
        records = create_drafts(
            records=records,
            template_path=_template,
            gog_account=gog_account,
            draft_log_path=_draft_log,
            filter_mode=draft_filter,
            firma_vars=firma_vars or {},
            dry_run=draft_dry_run,
        )

    metadata = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "despachos_total": len(selected),
        "publications_total": publications_total,
        "pdfs_total": pdfs_total,
        "enrichment_enabled": enrichment_enabled,
        "draft_emails_enabled": draft_emails,
        "sheets_report_enabled": sheets_report,
    }
    export_payload = build_export_payload(run_label=run_label, metadata=metadata, records=records)
    outputs = write_export_bundle(export_dir, export_payload)
    write_json(run_dir / "run_payload.json", {"run_label": run_label, "metadata": metadata, "records": records})
    write_json(diagnostics_dir / "publications.json", publications_manifest)
    write_json(diagnostics_dir / "selected_documents.json", selected_docs_manifest)
    write_json(diagnostics_dir / "pipeline_diagnostics.json", diagnostics)

    sheets_result: dict[str, Any] = {}
    if sheets_report and gog_account:
        logger.info("Exportando a Google Sheets...")
        try:
            sheets_result = export_to_sheets(
                run_label=run_label,
                records=records,
                account=gog_account,
                dry_run=sheets_dry_run,
            )
            logger.info("Sheets: %s", sheets_result.get("sheet_url", "dry-run"))
        except Exception as exc:
            logger.error("Sheets export fallido: %s", exc)
            sheets_result = {"error": str(exc)}

    result = {
        "run_label": run_label,
        "run_dir": str(run_dir),
        "metadata": metadata,
        "exports": outputs,
        "diagnostics": str(diagnostics_dir / "pipeline_diagnostics.json"),
        "sheets": sheets_result or None,
    }
    write_json(run_dir / "run_result.json", result)
    return result


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Flujo end-to-end para Medellín civil circuito")
    parser.add_argument("--fecha-inicio", required=True, type=valid_date)
    parser.add_argument("--fecha-fin", required=True, type=valid_date)
    parser.add_argument("--despacho-id", action="append", help="Filtra a uno o más despachos por ID exacto")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--no-db", action="store_true", help="Saltar enriquecimiento y persistencia en PostgreSQL")
    parser.add_argument("--draft-emails", action="store_true", help="Crear borradores Gmail para registros con email")
    parser.add_argument("--gog-account", help="Cuenta Gmail autenticada en gog")
    parser.add_argument(
        "--draft-filter",
        default="all_with_email",
        choices=["all_with_email", "accepted_and_review", "accepted_only"],
        help="Modo de filtro para creación de drafts",
    )
    parser.add_argument("--firma-nombre", default="[NOMBRE BUFETE]")
    parser.add_argument("--abogado-nombre", default="[NOMBRE DEL ABOGADO]")
    parser.add_argument("--abogado-telefono", default="")
    parser.add_argument("--abogado-email", default="")
    parser.add_argument("--draft-dry-run", action="store_true", help="Simula drafts sin crearlos en Gmail")
    parser.add_argument("--sheets-report", action="store_true", help="Exportar resultados a Google Sheets")
    parser.add_argument("--sheets-dry-run", action="store_true", help="Simula export a Sheets sin escribir nada")
    args = parser.parse_args()

    # Aplicar defaults de pipeline.yaml para valores no pasados por CLI
    d = _DEFAULTS
    enrich_2023 = args.enrich_file_2023 or str(PROJECT_ROOT / d.get("enrich_file_2023", ""))
    enrich_2025 = args.enrich_file_2025 or str(PROJECT_ROOT / d.get("enrich_file_2025", ""))
    draft_emails = args.draft_emails or bool(d.get("draft_emails", False))
    gog_account = args.gog_account or d.get("gog_account")
    draft_filter = args.draft_filter if args.draft_filter != "all_with_email" else d.get("draft_filter", "all_with_email")
    sheets_report = args.sheets_report or bool(d.get("sheets_report", False))

    firma_vars = {
        "firma_nombre": args.firma_nombre if args.firma_nombre != "[NOMBRE BUFETE]" else d.get("firma_nombre", "[NOMBRE BUFETE]"),
        "abogado_nombre": args.abogado_nombre if args.abogado_nombre != "[NOMBRE DEL ABOGADO]" else d.get("abogado_nombre", "[NOMBRE DEL ABOGADO]"),
        "abogado_telefono": args.abogado_telefono or d.get("abogado_telefono", ""),
        "abogado_email": args.abogado_email or d.get("abogado_email", ""),
    }

    try:
        validate_date(args.fecha_inicio)
        validate_date(args.fecha_fin)
        if args.despacho_id:
            for did in args.despacho_id:
                validate_despacho_id(did)
    except ValueError as exc:
        parser.error(str(exc))

    result = run_pipeline(
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin,
        despacho_ids=args.despacho_id,
        output_root=Path(args.output_root),
        no_db=args.no_db,
        draft_emails=draft_emails,
        gog_account=gog_account,
        draft_filter=draft_filter,
        firma_vars=firma_vars,
        draft_dry_run=args.draft_dry_run,
        sheets_report=sheets_report,
        sheets_dry_run=args.sheets_dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
