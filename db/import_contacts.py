"""Import/re-import a Cámara de Comercio TXT file into the contacts table.

Usage:
    python -m db.import_contacts --file /path/to/NACIONAL_2026.TXT --label colombia_2026
    python -m db.import_contacts --file /path/to/NACIONAL_2026.TXT --label colombia_2026 --replace
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

logger = logging.getLogger("legal_monitor.db.import_contacts")

# Allow running as `python -m db.import_contacts` from project root
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from db import SessionLocal
from db.models import Contact

# Import normalizer from scripts/
_scripts = _root / "scripts"
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from enrich_contacts import normalize_company_name  # noqa: E402

BATCH_SIZE = 5_000


def import_contacts(file_path: Path, label: str, replace: bool = False) -> int:
    session = SessionLocal()
    try:
        if replace:
            deleted = session.query(Contact).filter(Contact.source_label == label).delete()
            session.commit()
            print(f"Deleted {deleted:,} existing records with label '{label}'.")

        total = 0
        batch: list[Contact] = []

        with file_path.open("r", encoding="latin-1", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                razon_social = row.get("razon_social") or row.get("RAZON_SOCIAL") or ""
                # Try common column name variants
                if not razon_social:
                    for key in row:
                        if "razon" in key.lower() and "social" in key.lower():
                            razon_social = row[key]
                            break

                normalized = normalize_company_name(razon_social)
                if not normalized:
                    continue

                # Find correo_comercial column (case-insensitive)
                correo = None
                for key in row:
                    if "correo" in key.lower():
                        correo = row[key] or None
                        break

                contact = Contact(
                    razon_social=razon_social,
                    razon_social_normalizada=normalized,
                    correo_comercial=correo,
                    source_label=label,
                    raw_data=dict(row),
                )
                batch.append(contact)
                total += 1

                if len(batch) >= BATCH_SIZE:
                    try:
                        session.bulk_save_objects(batch)
                        session.commit()
                    except Exception:
                        session.rollback()
                        raise RuntimeError("Batch insert failed") from None
                    batch = []
                    print(f"  {total:,} records imported...", end="\r", flush=True)

        if batch:
            try:
                session.bulk_save_objects(batch)
                session.commit()
            except Exception:
                session.rollback()
                raise RuntimeError("Final batch insert failed") from None

        print(f"\nDone. Total imported: {total:,} records with label '{label}'.")
        return total

    finally:
        session.close()


def cli() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Importar TXT de Cámara de Comercio a PostgreSQL")
    parser.add_argument("--file", required=True, help="Ruta al archivo TXT")
    parser.add_argument("--label", required=True, help="Etiqueta para identificar el dataset (ej: colombia_2026)")
    parser.add_argument("--replace", action="store_true", help="Borrar registros previos con el mismo label antes de importar")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: archivo no encontrado: {file_path}", file=sys.stderr)
        sys.exit(1)

    import_contacts(file_path, args.label, replace=args.replace)


if __name__ == "__main__":
    cli()
