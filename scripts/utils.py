from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable


def ensure_parent(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path: str | Path, data: object) -> None:
    path = ensure_parent(path)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.chmod(path, 0o600)


def write_csv(path: str | Path, rows: Iterable[dict]) -> None:
    rows = list(rows)
    path = ensure_parent(path)
    if not rows:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        os.chmod(path, 0o600)
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            # Serialize list values as semicolon-separated strings for CSV compatibility
            writer.writerow({
                k: ";".join(v) if isinstance(v, list) else v
                for k, v in row.items()
            })
    os.chmod(path, 0o600)
