from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "data" / "runs"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_RETENTION_HOURS = 24


def age_hours(path: Path) -> float:
    return (time.time() - path.stat().st_mtime) / 3600


def remove_path(path: Path, dry_run: bool) -> None:
    if dry_run:
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)


def cleanup_runs(retention_hours: int, dry_run: bool = False) -> dict:
    summary = {
        "retention_hours": retention_hours,
        "dry_run": dry_run,
        "runs_scanned": 0,
        "runs_cleaned": 0,
        "pdf_dirs_removed": 0,
        "diagnostics_dirs_removed": 0,
        "raw_dirs_removed": 0,
        "items": [],
    }

    if RUNS_DIR.exists():
        for run_dir in sorted(RUNS_DIR.iterdir()):
            if not run_dir.is_dir():
                continue
            summary["runs_scanned"] += 1
            if age_hours(run_dir) < retention_hours:
                continue

            cleaned = False
            pdf_dir = run_dir / "pdfs"
            diagnostics_dir = run_dir / "diagnostics"

            if pdf_dir.exists():
                summary["pdf_dirs_removed"] += 1
                summary["items"].append({"action": "remove_dir", "path": str(pdf_dir)})
                remove_path(pdf_dir, dry_run)
                cleaned = True

            if diagnostics_dir.exists():
                summary["diagnostics_dirs_removed"] += 1
                summary["items"].append({"action": "remove_dir", "path": str(diagnostics_dir)})
                remove_path(diagnostics_dir, dry_run)
                cleaned = True

            if cleaned:
                summary["runs_cleaned"] += 1

    if RAW_DIR.exists():
        for raw_dir in sorted(RAW_DIR.iterdir()):
            if not raw_dir.is_dir():
                continue
            if age_hours(raw_dir) < retention_hours:
                continue
            summary["raw_dirs_removed"] += 1
            summary["items"].append({"action": "remove_dir", "path": str(raw_dir)})
            remove_path(raw_dir, dry_run)

    return summary


def cli() -> None:
    parser = argparse.ArgumentParser(description="Limpieza segura de runs y artefactos pesados")
    parser.add_argument("--retention-hours", type=int, default=DEFAULT_RETENTION_HOURS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    summary = cleanup_runs(retention_hours=args.retention_hours, dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
