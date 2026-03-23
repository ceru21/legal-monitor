# Cleanup Policy — legal-monitor

## Objetivo
Reducir el peso en disco sin perder resultados útiles.

## Se conserva
- `data/runs/*/exports/`
- `run_result.json`
- `run_payload.json`
- `input/` (archivos fuente externos)
- configuración y scripts

## Se elimina automáticamente después de 24 horas
- `data/runs/*/pdfs/`
- `data/runs/*/diagnostics/`
- `data/raw/*`

## Script
- `scripts/cleanup_runs.py`

## Ejecución manual
```bash
cd /root/.openclaw/workspace/legal-monitor
source .venv/bin/activate
python scripts/cleanup_runs.py --dry-run
python scripts/cleanup_runs.py
```
