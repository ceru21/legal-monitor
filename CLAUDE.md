# legal-monitor

## Que es este proyecto

Pipeline CLI en Python que automatiza el monitoreo de publicaciones procesales de juzgados civiles del circuito de Medellin. Consulta el portal de la Rama Judicial, descarga PDFs de planillas/estados, extrae registros estructurados y clasifica cuales son relevantes.

Sprint 1 (viabilidad): solo cubre los 22 despachos civiles del circuito de Medellin. Validado con 14 PDFs, 180 filas extraidas.

## Flujo del pipeline

```
CLI args (fechas, despacho_ids)
  -> PortalClient.search_html()       -> HTML con publicaciones
  -> extract_publications()           -> list[Publication]
  -> fetch_detail_documents()         -> list[DetailDocument]
  -> choose_primary_document()        -> PDF principal
  -> download_document()              -> archivo PDF en disco
  -> parse_pdf()                      -> list[ParsedRow]  (pdfplumber + coordenadas X)
  -> decide()                         -> MatchDecision (accepted/review/rejected)
  -> build_export_payload()
  -> write_export_bundle()            -> JSON + CSV en data/runs/
```

## Archivos

| Archivo | Rol |
|---------|-----|
| `scripts/run_search.py` | Orquestador principal CLI |
| `scripts/scraper_portal.py` | HTTP scraper del portal Rama Judicial |
| `scripts/parse_pdf.py` | Parser PDF con pdfplumber (coordenadas X para columnas) |
| `scripts/matcher.py` | Clasificador fuzzy con SequenceMatcher |
| `scripts/export_results.py` | Exportacion JSON/CSV |
| `scripts/models.py` | Dataclasses: Publication, DetailDocument, ParsedRow, MatchDecision, RunSummary |
| `scripts/utils.py` | normalize_text, sha256_file, write_json, write_csv |
| `config/pipeline.yaml` | Runtime config: timeouts, throttle, fuzzy thresholds |
| `config/target_patterns.yaml` | Patrones de proceso y actuacion a clasificar |
| `references/despachos_medellin_civil_circuito.json` | Lista de 22 despachos con IDs del portal |

## Como correr

```bash
pip install -r requirements.txt

# Corrida normal (todos los despachos)
python scripts/run_search.py --fecha-inicio 2026-03-18 --fecha-fin 2026-03-18

# Un solo despacho
python scripts/run_search.py --fecha-inicio 2026-03-18 --fecha-fin 2026-03-18 --despacho-id 050013103012
```

Salida: JSON en stdout + archivos en `data/runs/<run_label>/`.

Los logs de progreso van a stderr (INFO). El JSON final va a stdout y es parseable.

## Decisiones de clasificacion

- **accepted**: proceso_conf >= 0.90 AND/OR act_conf >= 0.90 (thresholds en `config/pipeline.yaml`)
- **review**: señal media (>= 0.80) o hint negativo ("inadmite demanda", etc.)
- **rejected**: sin señal

Los patrones (verbal, admite demanda, mandamiento de pago) se cargan de `config/target_patterns.yaml`.

## Dependencias

- `requests` — HTTP al portal
- `pdfplumber` — extraccion de texto y coordenadas del PDF
- `PyYAML` — lectura de configs

## Restricciones del Sprint 1 — NO hacer

- No multi-ciudad (solo Medellin civil circuito)
- No OCR (pdfplumber con texto nativo)
- No browser automation / Playwright
- No base de datos
- Los YAMLs de config SI se cargan (desde Sprint 2 en adelante)
