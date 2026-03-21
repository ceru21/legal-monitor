from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
import sys
from typing import Any, Iterable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from utils import write_csv, write_json


DETAIL_COLUMNS = [
    "run_label",
    "fecha_inicio",
    "fecha_fin",
    "despacho_id",
    "despacho",
    "publication_id",
    "fecha_publicacion",
    "titulo_publicacion",
    "publication_url",
    "pdf_label",
    "pdf_url",
    "pdf_path",
    "pdf_fingerprint",
    "pdf_page_number",
    "row_index",
    "radicado_raw",
    "radicado_normalizado",
    "tipo_proceso",
    "actuacion",
    "demandante",
    "demandado",
    "anotacion",
    "revision_manual",
    "parse_mode",
    "parse_confidence",
    "decision",
    "match_reason",
    "process_type_match",
    "actuacion_match",
    "process_type_confidence",
    "actuacion_confidence",
    "texto_fila_original",
]

OPERATIVE_COLUMNS = [
    "run_label",
    "fecha_inicio",
    "fecha_fin",
    "despacho_id",
    "despacho",
    "fecha_publicacion",
    "titulo_publicacion",
    "pdf_path",
    "radicado_normalizado",
    "tipo_proceso",
    "actuacion",
    "demandante",
    "demandado",
    "decision",
    "match_reason",
    "revision_manual",
    "process_type_match",
    "actuacion_match",
]

PDF_SUMMARY_COLUMNS = [
    "run_label",
    "despacho_id",
    "despacho",
    "fecha_publicacion",
    "titulo_publicacion",
    "pdf_label",
    "pdf_path",
    "rows_total",
    "accepted",
    "review",
    "rejected",
    "manual_review_yes",
]


def _select_columns(record: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    return {column: record.get(column) for column in columns}


def build_export_payload(run_label: str, metadata: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, Any]:
    detailed_rows = [_select_columns(record, DETAIL_COLUMNS) for record in records]
    operative_rows = [
        _select_columns(record, OPERATIVE_COLUMNS)
        for record in records
        if record.get("decision") in {"accepted", "review"}
    ]

    grouped: dict[tuple[str | None, str | None], list[dict[str, Any]]] = {}
    for record in records:
        key = (record.get("pdf_path"), record.get("despacho_id"))
        grouped.setdefault(key, []).append(record)

    pdf_summaries: list[dict[str, Any]] = []
    for rows in grouped.values():
        first = rows[0]
        decisions = Counter((row.get("decision") or "unknown") for row in rows)
        pdf_summaries.append(
            {
                "run_label": run_label,
                "despacho_id": first.get("despacho_id"),
                "despacho": first.get("despacho"),
                "fecha_publicacion": first.get("fecha_publicacion"),
                "titulo_publicacion": first.get("titulo_publicacion"),
                "pdf_label": first.get("pdf_label"),
                "pdf_path": first.get("pdf_path"),
                "rows_total": len(rows),
                "accepted": decisions.get("accepted", 0),
                "review": decisions.get("review", 0),
                "rejected": decisions.get("rejected", 0),
                "manual_review_yes": sum(1 for row in rows if (row.get("revision_manual") or "").lower() == "si"),
            }
        )

    global_decisions = Counter((record.get("decision") or "unknown") for record in records)
    summary = {
        "run_label": run_label,
        "fecha_inicio": metadata.get("fecha_inicio"),
        "fecha_fin": metadata.get("fecha_fin"),
        "despachos_total": metadata.get("despachos_total", 0),
        "publications_total": metadata.get("publications_total", 0),
        "pdfs_total": metadata.get("pdfs_total", 0),
        "rows_total": len(records),
        "accepted": global_decisions.get("accepted", 0),
        "review": global_decisions.get("review", 0),
        "rejected": global_decisions.get("rejected", 0),
        "manual_review_yes": sum(1 for record in records if (record.get("revision_manual") or "").lower() == "si"),
    }

    return {
        "summary": summary,
        "pdf_summaries": pdf_summaries,
        "records": detailed_rows,
        "operative_records": operative_rows,
    }


def write_export_bundle(base_dir: str | Path, payload: dict[str, Any]) -> dict[str, str]:
    base_dir = Path(base_dir)
    write_json(base_dir / "summary.json", payload["summary"])
    write_json(base_dir / "pdf_summaries.json", payload["pdf_summaries"])
    write_json(base_dir / "records_detailed.json", payload["records"])
    write_json(base_dir / "records_operativos.json", payload["operative_records"])
    write_csv(base_dir / "pdf_summaries.csv", (_select_columns(row, PDF_SUMMARY_COLUMNS) for row in payload["pdf_summaries"]))
    write_csv(base_dir / "records_detailed.csv", payload["records"])
    write_csv(base_dir / "records_operativos.csv", payload["operative_records"])
    return {
        "summary_json": str(base_dir / "summary.json"),
        "pdf_summaries_json": str(base_dir / "pdf_summaries.json"),
        "records_detailed_json": str(base_dir / "records_detailed.json"),
        "records_operativos_json": str(base_dir / "records_operativos.json"),
        "pdf_summaries_csv": str(base_dir / "pdf_summaries.csv"),
        "records_detailed_csv": str(base_dir / "records_detailed.csv"),
        "records_operativos_csv": str(base_dir / "records_operativos.csv"),
    }


def cli() -> None:
    parser = argparse.ArgumentParser(description="Exporta resultados detallados y operativos a JSON/CSV")
    parser.add_argument("input_json", help="JSON con llaves: run_label, metadata, records")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    input_payload = json.loads(Path(args.input_json).read_text(encoding="utf-8"))
    payload = build_export_payload(
        run_label=input_payload["run_label"],
        metadata=input_payload.get("metadata", {}),
        records=input_payload.get("records", []),
    )
    outputs = write_export_bundle(args.out_dir, payload)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
