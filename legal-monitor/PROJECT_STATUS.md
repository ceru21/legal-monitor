# PROJECT_STATUS.md — legal-monitor

## Objetivo del proyecto
Construir un pipeline que consulte el portal de Publicaciones Procesales de la Rama Judicial, filtre despachos civiles del circuito de Medellín por rango de fechas, descargue sus planillas/PDFs, extraiga registros estructurados y seleccione los casos relevantes para uso posterior.

---

# Estado general

## Situación actual
El proyecto ya es **viable y funcional en versión inicial**, pero **todavía no está terminado**.

### Ya probado
- descubrimiento del portal
- consulta automática de despachos
- descarga de PDFs
- parser inicial
- matcher inicial
- validación sobre múltiples despachos reales

### Todavía pendiente
- endurecer parser en formatos raros
- validar más juzgados/fechas
- mejorar calidad de `revision_manual`
- exportación final operativa y corrida de extremo a extremo

---

# Fases del proyecto

## Fase 1 — Descubrimiento del portal
### Objetivo
Entender cómo funciona el portal y cómo automatizarlo.

### Incluye
- filtros
- secuencia del formulario
- paginación
- detalle de publicaciones
- resolución del PDF principal

### Estado
**✅ Hecha**

### Entregables ya existentes
- `references/portal-contract.md`
- `references/despachos_medellin_civil_circuito.json`

---

## Fase 2 — Scraper del portal
### Objetivo
Automatizar la búsqueda de publicaciones por despacho y fechas.

### Incluye
- Antioquia
- Medellín
- Juzgado de Circuito
- Civil
- despacho por despacho
- rango de fechas
- captura de publicaciones
- entrada al detalle

### Estado
**✅ Hecha (versión inicial funcional)**

### Entregables ya existentes
- `scripts/scraper_portal.py`

---

## Fase 3 — Descarga de PDFs
### Objetivo
Resolver y guardar la planilla/PDF principal de cada publicación.

### Incluye
- identificar PDF principal
- descargar PDF real
- guardar muestra local
- preparar lote para validación

### Estado
**✅ Hecha (versión inicial funcional)**

---

## Fase 4 — Parser del PDF
### Objetivo
Convertir el PDF en registros estructurados.

### Campos objetivo
- radicado
- tipo de proceso
- actuación
- demandante
- demandado
- `revision_manual`

### Estado
**🟡 En progreso avanzado**

### Ya logrado
- extracción de radicado
- extracción de tipo de proceso
- extracción de actuación
- mejora importante en demandante/demandado
- soporte inicial a formatos distintos
- soporte a variante tipo `Tutelas`

### Pendiente en esta fase
- robustecer edge cases
- limpiar mejor registros contaminados por pie de página
- mejorar calidad en formatos con columnas desplazadas

### Entregables ya existentes
- `scripts/parse_pdf.py`

---

## Fase 5 — Matcher / filtro jurídico-operativo
### Objetivo
Seleccionar solo los registros relevantes.

### Señales objetivo actuales
- `Verbal`
- `Verbal sumario`
- `Auto admite`
- `Auto admite demanda`
- `Auto libra mandamiento`

### Estado
**✅ Hecha (versión inicial funcional)**

### Ya logrado
- clasificación `accepted / review / rejected`
- tratamiento de negativos como `inadmite demanda`
- integración con `revision_manual`

### Entregables ya existentes
- `scripts/matcher.py`

---

## Fase 6 — Validación con múltiples muestras
### Objetivo
Comprobar que no solo funciona con un PDF, sino con varios despachos y formatos.

### Estado
**🟡 En progreso**

### Ya logrado
Primer lote validado sobre 5 despachos:
- Juzgado 001 → manual review: 2
- Juzgado 002 → manual review: 1
- Juzgado 003 → manual review: 3
- Juzgado 004 → manual review: 0
- Juzgado 005 → manual review: 2

### Hallazgo importante
El Juzgado 001 tenía formato tipo `Tutelas`; después de ajustar esa variante, la revisión manual bajó de 7 a 2.

### Pendiente en esta fase
- ampliar a más despachos
- cubrir más fechas
- guardar benchmark por PDF
- identificar formatos recurrentes
- medir estabilidad del parser

---

## Fase 7 — Exportación final útil para operación
### Objetivo
Dejar salida limpia y utilizable.

### Incluye
- JSON final
- CSV final
- campos completos
- registros relevantes
- salida revisable por humanos

### Estado
**⏳ Pendiente / parcial**

### Falta
- normalizar exportes
- consolidar salida final por lote
- dejar formato listo para operación

---

## Fase 8 — Orquestación end-to-end
### Objetivo
Correr todo como pipeline completo.

### Flujo esperado
1. consultar portal
2. descargar PDFs
3. parsear
4. filtrar
5. exportar

### Estado
**⏳ Pendiente**

### Falta
- `run_search.py` o equivalente de orquestación final
- ejecución completa desde una sola entrada
- logs de corrida consolidados

---

# Qué falta para continuar

## Prioridad 1
### Terminar Fase 6
- probar más PDFs
- ampliar despachos
- revisar fechas adicionales
- identificar patrones de falla

## Prioridad 2
### Endurecer Fase 4
- bajar `revision_manual`
- limpiar registros contaminados
- mejorar demandante/demandado en layouts raros

## Prioridad 3
### Cerrar Fase 7
- dejar exportación final limpia
- generar salida operativa en CSV/JSON

## Prioridad 4
### Cerrar Fase 8
- construir corrida completa de extremo a extremo

---

# Ruta recomendada para seguir

## Siguiente paso recomendado
1. correr validación sobre más PDFs
2. clasificar variantes de formato
3. ajustar parser según variantes
4. rerun del lote
5. consolidar exportación final
6. armar orquestador final

---

# Resumen ejecutivo

## Hecho
- portal
- scraper
- descarga
- parser inicial
- matcher inicial
- validación inicial multi-muestra

## En progreso
- robustez del parser
- validación multi-formato

## Pendiente
- exportación final limpia
- orquestación completa
- validación extendida

---

# Archivos clave del proyecto
- `SPRINT_1.md`
- `PROJECT_STATUS.md`
- `references/portal-contract.md`
- `references/despachos_medellin_civil_circuito.json`
- `scripts/scraper_portal.py`
- `scripts/parse_pdf.py`
- `scripts/matcher.py`
