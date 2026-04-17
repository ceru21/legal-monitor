from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from db import get_connection
from utils import normalize_text, write_csv, write_json

CORP_SUFFIXES = [
    " s a s", " s a", " sas", " sa", " ltda", " limitada", " s en c", " s c a",
    " sociedad anonima", " sociedad por acciones simplificada", " y cia", " y compania",
]


def normalize_company_name(value: str | None) -> str:
    text = normalize_text(value or "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    for suffix in CORP_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return text


def split_emails(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[\s,;]+", raw.strip())
    emails = []
    for part in parts:
        part = part.strip()
        if "@" in part:
            emails.append(part)
    seen = []
    for email in emails:
        if email not in seen:
            seen.append(email)
    return seen


def _chunked(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


def load_contact_index_from_db(names: list[str], database_url: str | None = None) -> dict[str, dict[str, Any]]:
    normalized_names = []
    seen = set()
    for name in names:
        normalized = normalize_company_name(name)
        if normalized and normalized not in seen:
            seen.add(normalized)
            normalized_names.append(normalized)

    index: dict[str, dict[str, Any]] = {}
    if not normalized_names:
        return index

    query = """
        SELECT razon_social_normalizada, razon_social, correo_comercial, source_label, raw_data
        FROM contacts
        WHERE razon_social_normalizada = ANY(%s)
    """

    with get_connection(database_url) as conn:
        with conn.cursor() as cur:
            for batch in _chunked(normalized_names):
                cur.execute(query, (batch,))
                for razon_social_normalizada, razon_social, correo_comercial, source_label, raw_data in cur.fetchall():
                    entry = index.setdefault(
                        razon_social_normalizada,
                        {
                            "rows": [],
                            "emails": [],
                            "source_labels": [],
                            "source_emails": defaultdict(list),
                        },
                    )
                    entry["rows"].append(
                        {
                            "razon_social": razon_social,
                            "correo_comercial": correo_comercial,
                            "source_label": source_label,
                            "raw_data": raw_data,
                        }
                    )
                    if source_label and source_label not in entry["source_labels"]:
                        entry["source_labels"].append(source_label)
                    for email in split_emails(correo_comercial):
                        if email not in entry["emails"]:
                            entry["emails"].append(email)
                        if source_label and email not in entry["source_emails"][source_label]:
                            entry["source_emails"][source_label].append(email)

    return index


def enrich_record(record: dict[str, Any], db_index: dict[str, Any]) -> dict[str, Any]:
    demandado = record.get("demandado")
    key = normalize_company_name(demandado)
    match = db_index.get(key)
    all_emails = match["emails"] if match else []
    source_labels = match["source_labels"] if match else []
    found_cc = bool(match)

    return {
        **record,
        "found_cc": found_cc,
        "match_db": bool(all_emails),
        "email_db": ", ".join(all_emails) if all_emails else None,
        "source_labels": source_labels,
        "emails_encontrados": all_emails,
        "match_total": bool(all_emails),
        "demandado_normalizado_match": key,
    }


def enrich_records(records: list[dict[str, Any]], database_url: str | None = None) -> list[dict[str, Any]]:
    db_index = load_contact_index_from_db([record.get("demandado", "") for record in records], database_url=database_url)
    return [enrich_record(record, db_index) for record in records]


def cli() -> None:
    parser = argparse.ArgumentParser(description="Enriquece registros operativos con correos desde PostgreSQL")
    parser.add_argument("records_json", help="Archivo JSON de registros operativos")
    parser.add_argument("--database-url", help="Sobrescribe DATABASE_URL para la consulta")
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-csv")
    args = parser.parse_args()

    records = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
    enriched = enrich_records(records, database_url=args.database_url)
    write_json(args.out_json, enriched)
    if args.out_csv:
        write_csv(args.out_csv, enriched)
    print(json.dumps({
        "records": len(enriched),
        "match_total": sum(1 for row in enriched if row.get("match_total")),
        "match_db": sum(1 for row in enriched if row.get("match_db")),
        "out_json": args.out_json,
        "out_csv": args.out_csv,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
