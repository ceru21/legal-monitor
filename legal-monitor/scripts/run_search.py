from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from enrich_contacts import enrich_records
from export_results import build_export_payload, write_export_bundle
from matcher import decide
from parse_pdf import parse_pdf
from scraper_portal import DetailDocument, PortalClient, Publication
from utils import normalize_text, write_json

PROJECT_ROOT = SCRIPT_DIR.parent
REFERENCE_DESPACHOS = PROJECT_ROOT / "references" / "despachos_medellin_civil_circuito.json"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "runs"


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
    enrich_file_2023: str | None = None,
    enrich_file_2025: str | None = None,
) -> dict[str, Any]:
    client = PortalClient()
    scope = load_scope_despachos()
    if despacho_ids:
        selected = [item for item in scope if item["id"] in set(despacho_ids)]
    else:
        selected = scope

    run_label = f"medellin_civil_circuito_{fecha_inicio}_a_{fecha_fin}_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}"
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

    for despacho in selected:
        despacho_id = despacho["id"]
        html_text = client.search_html(fecha_inicio, fecha_fin, id_despacho=despacho_id)
        publications = client.extract_publications(html_text)
        publications_total += len(publications)
        publications_manifest.extend({"despacho_id": despacho_id, **publication.to_dict()} for publication in publications)

        if not publications:
            diagnostics.append({"despacho_id": despacho_id, "despacho": despacho["nombre"], "status": "no_publications"})
            continue

        for publication in publications:
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

            parsed_rows = [row.to_dict() for row in parse_pdf(pdf_path)]
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

    if enrich_file_2023 and enrich_file_2025:
        records = enrich_records(records, enrich_file_2023, enrich_file_2025)

    metadata = {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "despachos_total": len(selected),
        "publications_total": publications_total,
        "pdfs_total": pdfs_total,
        "enrichment_enabled": bool(enrich_file_2023 and enrich_file_2025),
    }
    export_payload = build_export_payload(run_label=run_label, metadata=metadata, records=records)
    outputs = write_export_bundle(export_dir, export_payload)
    write_json(run_dir / "run_payload.json", {"run_label": run_label, "metadata": metadata, "records": records})
    write_json(diagnostics_dir / "publications.json", publications_manifest)
    write_json(diagnostics_dir / "selected_documents.json", selected_docs_manifest)
    write_json(diagnostics_dir / "pipeline_diagnostics.json", diagnostics)

    result = {
        "run_label": run_label,
        "run_dir": str(run_dir),
        "metadata": metadata,
        "exports": outputs,
        "diagnostics": str(diagnostics_dir / "pipeline_diagnostics.json"),
    }
    write_json(run_dir / "run_result.json", result)
    return result


def cli() -> None:
    parser = argparse.ArgumentParser(description="Flujo end-to-end para Medellín civil circuito")
    parser.add_argument("--fecha-inicio", required=True)
    parser.add_argument("--fecha-fin", required=True)
    parser.add_argument("--despacho-id", action="append", help="Filtra a uno o más despachos por ID exacto")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    parser.add_argument("--enrich-file-2023")
    parser.add_argument("--enrich-file-2025")
    args = parser.parse_args()

    result = run_pipeline(
        fecha_inicio=args.fecha_inicio,
        fecha_fin=args.fecha_fin,
        despacho_ids=args.despacho_id,
        output_root=Path(args.output_root),
        enrich_file_2023=args.enrich_file_2023,
        enrich_file_2025=args.enrich_file_2025,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
