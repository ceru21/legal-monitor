# Sprint 1 — Descubrimiento + Viabilidad técnica del portal y PDFs

## Objetivo del sprint
Validar de extremo a extremo que el sistema puede:
1. descubrir despachos civiles del circuito de Medellín en el portal
2. consultar publicaciones por rango de fechas
3. resolver enlaces a PDFs
4. descargar PDFs reales
5. parsear al menos un subconjunto útil
6. detectar coincidencias iniciales por tipo de proceso y actuación
7. exportar resultados a JSON y CSV

---

## Estado general
- [x] Especificación final v1.0 redactada
- [x] Estructura base del proyecto creada
- [x] Configuración inicial creada
- [x] Lista de tareas del sprint definida
- [x] Descubrimiento técnico del portal completado
- [x] Canonización de despachos implementada
- [x] Scraper inicial implementado
- [x] Descarga real de PDFs funcionando
- [x] Parser inicial de PDFs funcionando
- [x] Matcher inicial funcionando
- [ ] Orquestador `run_search.py` funcionando
- [x] Dataset mínimo de prueba reunido
- [ ] Ground truth inicial creado
- [ ] Exportación CSV/JSON validada
- [ ] Sprint demo listo

---

## Backlog ejecutable

### Fase A — Descubrimiento del portal

#### A1. Documentar contrato real del portal
- [x] Abrir portal por inspección HTTP/HTML
- [x] Documentar orden exacto de filtros
- [x] Identificar selectores robustos
- [x] Confirmar si los dropdowns son AJAX/dependientes
- [x] Confirmar cómo aparece el link al PDF
- [x] Confirmar si hay paginación del portal
- [x] Guardar hallazgos en `references/portal-contract.md`

**Definition of Done**
- Existe `references/portal-contract.md`
- Tiene selectores, flujo, edge cases y ejemplo de resultado

#### A2. Descubrir despachos disponibles
- [x] Obtener lista completa de despachos para Antioquia / Medellín / Juzgado de Circuito / Civil
- [x] Guardar lista canonizada en JSON de referencia temporal
- [x] Validar que los nombres sean reutilizables por el scraper

**Definition of Done**
- Existe una lista de despachos resoluble por nombre normalizado

---

### Fase B — Scaffolding técnico

#### B1. Modelos y contratos internos
- [ ] Implementar `scripts/models.py`
- [ ] Definir modelos: `Publication`, `ParsedRow`, `MatchDecision`, `RunSummary`
- [ ] Definir contratos mínimos entre módulos

**Definition of Done**
- Los modelos existen y son importables

#### B2. Utilidades compartidas
- [ ] Implementar `scripts/utils.py`
- [ ] Agregar helpers para fechas
- [ ] Agregar normalización de texto
- [ ] Agregar hash SHA-256 para PDFs
- [ ] Agregar helpers de escritura JSON/CSV

**Definition of Done**
- Utilidades reutilizables disponibles y testeables

---

### Fase C — Scraper inicial

#### C1. Navegación base del portal
- [ ] Implementar `scripts/scraper_portal.py`
- [ ] Abrir portal con Playwright
- [ ] Aplicar filtros base
- [ ] Resolver un despacho específico
- [ ] Aplicar rango de fechas
- [ ] Lanzar consulta

**Definition of Done**
- El script consulta 1 despacho y retorna publicaciones estructuradas

#### C2. Extracción de publicaciones
- [x] Leer la lista de resultados
- [x] Extraer título, fecha, URL intermedia y/o PDF URL
- [ ] Manejar cero resultados sin fallar
- [ ] Manejar paginación del portal si existe

**Definition of Done**
- Devuelve `Publication[]` consistente

#### C3. Descarga de PDF
- [ ] Resolver PDF URL real
- [ ] Descargar PDF localmente
- [ ] Calcular `pdf_fingerprint`
- [ ] Evitar reprocesamiento del mismo archivo

**Definition of Done**
- [x] Se descargan al menos 3 PDFs reales y quedan guardados localmente
- Validación más reciente: 14 PDFs principales descargados/parseados al recorrer los 22 despachos para `2026-03-18`

---

### Fase D — Parser inicial

#### D1. Parser por tablas
- [x] Implementar `scripts/parse_pdf.py`
- [ ] Intentar `pdfplumber.extract_tables()`
- [x] Normalizar filas extraídas
- [x] Conservar `raw_columns` y `texto_fila_original`

**Definition of Done**
- [x] El parser devuelve filas parseadas para al menos 1 PDF real
- Validación actual del parser sobre el lote de `2026-03-18`: 180 filas extraídas, `revision_manual` reducido de 20 a 6

#### D2. Fallback por texto
- [ ] Extraer texto por página cuando no haya tabla utilizable
- [ ] Reconstruir filas por líneas o bloques
- [ ] Marcar `parse_mode=text`

**Definition of Done**
- Al menos 1 PDF problemático produce filas útiles por fallback

#### D3. Extracción de campos
- [ ] Intentar extraer `radicado_raw`
- [ ] Intentar extraer `radicado_normalizado`
- [ ] Intentar extraer demandante/demandado/tipo_proceso/actuación/anotación
- [ ] Calcular `parse_confidence`

**Definition of Done**
- Los registros contienen campos mínimos o texto crudo suficiente para revisión

---

### Fase E — Matching inicial

#### E1. Configurar patrones
- [x] Completar `config/target_patterns.yaml`
- [x] Separar `process_type_patterns` y `actuacion_patterns`
- [x] Agregar reglas iniciales de negocio

**Definition of Done**
- Los patrones están definidos en YAML y cargan sin error

#### E2. Implementar matcher
- [x] Implementar `scripts/matcher.py`
- [x] Normalizar texto
- [x] Aplicar exact/contains/regex/fuzzy
- [x] Devolver `accepted/review/rejected`

**Definition of Done**
- [x] Ejemplos positivos y negativos básicos se clasifican correctamente

---

### Fase F — Orquestación

#### F1. Integrar flujo completo
- [ ] Implementar `scripts/run_search.py`
- [ ] Parsear argumentos CLI
- [ ] Llamar scraper
- [ ] Descargar PDFs
- [ ] Parsear filas
- [ ] Aplicar matcher
- [ ] Exportar resultados

**Definition of Done**
- Un comando CLI produce salida de punta a punta

#### F2. Exportaciones y logs
- [ ] Guardar JSON detallado
- [ ] Guardar CSV operativo
- [ ] Guardar log resumen de ejecución
- [ ] Guardar errores por publicación/PDF

**Definition of Done**
- La corrida deja artefactos auditables en `data/`

---

### Fase G — Validación

#### G1. Dataset de prueba
- [ ] Reunir mínimo 10 PDFs reales
- [ ] Cubrir al menos 3 despachos
- [ ] Cubrir al menos 3 fechas distintas
- [ ] Guardar muestras en `tests/sample_pdfs/`

**Definition of Done**
- El corpus mínimo existe localmente

#### G2. Ground truth
- [ ] Crear `tests/ground_truth.json`
- [ ] Etiquetar manualmente matches esperados por PDF
- [ ] Registrar casos ambiguos

**Definition of Done**
- Existe una verdad terreno mínima para comparar resultados

#### G3. Tests básicos
- [ ] Implementar `tests/test_normalization.py`
- [ ] Implementar `tests/test_matcher.py`
- [ ] Implementar `tests/test_parser.py`

**Definition of Done**
- Las pruebas básicas corren localmente y validan funciones críticas

---

## Comando objetivo del sprint

```bash
python scripts/run_search.py \
  --fecha-inicio 2026-03-18 \
  --fecha-fin 2026-03-18 \
  --despacho-id 050013103012
```

---

## Criterio de salida del Sprint 1

El sprint se considera exitoso si, para al menos 1 despacho real:
- [ ] el portal se consulta automáticamente
- [ ] se encuentran publicaciones reales
- [ ] se descargan PDFs reales
- [ ] se parsean filas útiles
- [ ] se detectan matches iniciales
- [ ] se exporta JSON/CSV
- [ ] quedan logs suficientes para depurar

---

## Notas de ejecución
- Priorizar precisión y trazabilidad sobre cobertura total
- No meter OCR salvo que sea estrictamente necesario
- No escalar a multi-ciudad en este sprint
- Si el portal rompe selectores, actualizar primero `references/portal-contract.md`

## Corte de estado de esta pasada
- Se recorrieron los 22 despachos civiles del circuito de Medellín para la fecha `2026-03-18`
- 16 despachos tuvieron publicaciones y 14 PDFs principales fueron parseables con el selector actual
- Hallazgos de layout que generaban ruido:
  - pie de página incrustado en la última fila del PDF
  - actuaciones válidas redactadas como texto resolutivo (`Aprobar...`, `Tutelar...`) en vez de empezar por `Auto`
  - clases reales no contempladas todavía en la lista base (`Ordinario`, `Ejecutivo Singular`, `Reorganización Empresarial`)
- Resultado del ajuste actual en `scripts/parse_pdf.py`:
  - lote completo: `revision_manual` **20 → 6**
  - Juzgado 003: **3 → 0**
  - Juzgado 013: **4 → 1**
  - Juzgado 021: **2 → 0**
- Caso que sigue justificando revisión manual en el foco: Juzgado 013, fila con actuación truncada en `"a la Oficina de Apoyo Judicial para reparto."`
e Apoyo Judicial para reparto."`
