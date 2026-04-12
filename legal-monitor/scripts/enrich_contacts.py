from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

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


def load_contact_index(path: str | Path) -> dict[str, dict[str, Any]]:
    path = Path(path)
    index: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="latin-1", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            normalized = normalize_company_name(row.get("razon_social"))
            if not normalized:
                continue
            entry = index.setdefault(normalized, {"rows": [], "emails": []})
            entry["rows"].append(row)
            for email in split_emails(row.get("correo_comercial")):
                if email not in entry["emails"]:
                    entry["emails"].append(email)
    return index


def enrich_record(record: dict[str, Any], idx2023: dict[str, Any], idx2025: dict[str, Any]) -> dict[str, Any]:
    demandado = record.get("demandado")
    key = normalize_company_name(demandado)
    m2023 = idx2023.get(key)
    m2025 = idx2025.get(key)
    emails_2023 = m2023["emails"] if m2023 else []
    emails_2025 = m2025["emails"] if m2025 else []
    all_emails = []
    for email in emails_2023 + emails_2025:
        if email not in all_emails:
            all_emails.append(email)
    # found_cc = True si la empresa aparece en el directorio CC aunque no tenga email
    found_cc = bool(m2023 or m2025)
    return {
        **record,
        "found_cc": found_cc,
        "match_2023": bool(emails_2023),
        "email_2023": ", ".join(emails_2023) if emails_2023 else None,
        "match_2025": bool(emails_2025),
        "email_2025": ", ".join(emails_2025) if emails_2025 else None,
        "emails_encontrados": all_emails,
        "match_total": bool(all_emails),
        "demandado_normalizado_match": key,
    }


def enrich_records(records: list[dict[str, Any]], file_2023: str | Path, file_2025: str | Path) -> list[dict[str, Any]]:
    idx2023 = load_contact_index(file_2023)
    idx2025 = load_contact_index(file_2025)
    return [enrich_record(record, idx2023, idx2025) for record in records]


def cli() -> None:
    parser = argparse.ArgumentParser(description="Enriquece registros operativos con correos de archivos 2023/2025")
    parser.add_argument("records_json", help="Archivo JSON de registros operativos")
    parser.add_argument("--file-2023", required=True)
    parser.add_argument("--file-2025", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-csv")
    args = parser.parse_args()

    records = json.loads(Path(args.records_json).read_text(encoding="utf-8"))
    enriched = enrich_records(records, args.file_2023, args.file_2025)
    write_json(args.out_json, enriched)
    if args.out_csv:
        write_csv(args.out_csv, enriched)
    print(json.dumps({
        "records": len(enriched),
        "match_total": sum(1 for row in enriched if row.get("match_total")),
        "match_2023": sum(1 for row in enriched if row.get("match_2023")),
        "match_2025": sum(1 for row in enriched if row.get("match_2025")),
        "out_json": args.out_json,
        "out_csv": args.out_csv,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
