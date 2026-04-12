# Estado para Cesar — legal-monitor

## Plan en ejecución
Estamos implementando el Sprint 1 del proyecto `legal-monitor` para el portal de Publicaciones Procesales de la Rama Judicial.

### Objetivo del Sprint 1
Validar de extremo a extremo que el sistema puede:
1. descubrir despachos civiles del circuito de Medellín
2. consultar publicaciones por rango de fechas
3. resolver enlaces a PDFs
4. descargar PDFs reales
5. extraer datos iniciales del PDF
6. preparar matching y exportación

## Avance actual
### Completado
- Especificación final v1.0 redactada
- Sprint 1 convertido en checklist ejecutable
- Descubrimiento técnico del portal documentado
- Lista canonizada de 22 juzgados civiles del circuito de Medellín
- Scraper inicial implementado
- Consulta real probada contra un despacho
- Extracción de publicaciones y documentos del detalle funcionando

### Paso actual
**C3 + D1**
- C3: descarga de PDF real
- D1: parser inicial del PDF principal

## Evidencia real ya obtenida
- Se consultó el despacho `050013103012 - JUZGADO 012 CIVIL DEL CIRCUITO DE MEDELLÍN`
- Fecha consultada: `2026-03-18`
- Se encontraron publicaciones reales
- Se entró al detalle y se detectó como principal: `Planilla Estados Nro. 041.pdf`
- El PDF ya fue descargado como muestra real

## Estado técnico actual
Se validó un entorno Python local dentro de `legal-monitor/.venv` con `pdfplumber` disponible para el parser inicial.

## Evidencia de validación
- `scripts/parse_pdf.py` ejecutó correctamente sobre `data/raw/pdfs/sample_041.pdf`
- Se generó salida parseada con 16 filas
- `scripts/matcher.py` ejecutó correctamente sobre la salida parseada
- Resultado de matching sobre muestra: 5 `accepted`, 1 `review`, 10 `rejected`

## Siguiente paso inmediato
1. integrar scraper + descarga + parser + matcher en un flujo único
2. implementar exportación consolidada JSON/CSV
3. ampliar el corpus de prueba con más PDFs reales
4. refinar reglas de matching y ground truth

## Archivos relevantes
- `legal-monitor/SPRINT_1.md`
- `legal-monitor/references/portal-contract.md`
- `legal-monitor/references/despachos_medellin_civil_circuito.json`
- `legal-monitor/scripts/scraper_portal.py`
- `legal-monitor/scripts/models.py`
- `legal-monitor/scripts/utils.py`

## Commits recientes
- `072418d` — Add legal monitor sprint 1 plan and initial config
- `777a8a5` — Document portal discovery and Medellin civil court list
- `f6df8a3` — Implement initial portal scraper and shared models
72418d` — Add legal monitor sprint 1 plan and initial config
- `777a8a5` — Document portal discovery and Medellin civil court list
- `f6df8a3` — Implement initial portal scraper and shared models
