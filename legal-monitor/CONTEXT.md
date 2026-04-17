# CONTEXT.md — legal-monitor

## Qué es esto
`legal-monitor` es un pipeline para consultar publicaciones procesales de la Rama Judicial, extraer registros de PDFs, filtrar casos relevantes, enriquecer demandados con una base externa y exportar resultados operativos.

Está pensado como producto para bufetes, no como bot generalista.

---

## Objetivo del producto
Dado un rango de fechas y uno o varios despachos civiles del circuito de Medellín, el sistema debe:
1. consultar el portal
2. encontrar publicaciones
3. descargar la planilla principal en PDF
4. parsear registros
5. filtrar casos relevantes
6. cruzar el **demandado** con bases de Cámara de Comercio (2023 / 2025)
7. devolver resultados con email(s) cuando existan
8. opcionalmente generar borradores en Gmail (fase comercial final)

---

## Alcance actual
### Jurisdicción / alcance funcional
- Antioquia
- Medellín
- Juzgado de Circuito
- Civil
- despachos civiles del circuito de Medellín

### Filtro actual de relevancia
Se consideran señales relevantes principalmente en:
- `Verbal`
- `Verbal sumario`
- `Auto admite`
- `Auto admite demanda`
- `Auto libra mandamiento`
- variantes cercanas

### Negativos / revisión
Casos como:
- `inadmite demanda`
- `rechaza demanda`
- `niega mandamiento`
no entran como positivos limpios; van a `review` o se descartan.

---

## Componentes implementados
### 1. Descubrimiento del portal
- documentado en `references/portal-contract.md`
- lista de despachos en `references/despachos_medellin_civil_circuito.json`

### 2. Scraper
- archivo: `scripts/scraper_portal.py`
- hace búsqueda por fechas y despacho
- entra a detalle
- detecta documentos descargables
- identifica PDF principal

### 3. Parser
- archivo: `scripts/parse_pdf.py`
- extrae:
  - radicado
  - tipo de proceso
  - actuación
  - demandante
  - demandado
  - `revision_manual`
- ya soporta varias variantes de formato
- se endureció contra:
  - contaminación por pie de página
  - variantes tipo tutela
  - actuaciones no-`Auto`

### 4. Matcher
- archivo: `scripts/matcher.py`
- clasifica en:
  - `accepted`
  - `review`
  - `rejected`

### 5. Exportación
- archivo: `scripts/export_results.py`
- genera:
  - `summary.json`
  - `pdf_summaries.json/csv`
  - `records_detailed.json/csv`
  - `records_operativos.json/csv`

### 6. Orquestación end-to-end
- archivo: `scripts/run_search.py`
- flujo:
  1. search
  2. selección del PDF principal
  3. descarga
  4. parse
  5. match
  6. export
  7. enriquecimiento opcional

### 7. Enriquecimiento por base externa
- archivo: `scripts/enrich_contacts.py`
- cruza **solo contra el demandado**
- consulta PostgreSQL sobre la tabla `contacts`
- usa `contacts.razon_social_normalizada` para el match
- toma `correo_comercial` y `source_label`
- agrega:
  - `match_db`
  - `email_db`
  - `source_labels`
  - `emails_encontrados`
  - `match_total`

### 8. Limpieza automática
- archivo: `scripts/cleanup_runs.py`
- cron diario instalado
- conserva exportes útiles
- borra PDFs/diagnósticos viejos

---

## Ubicación de archivos importantes
### Proyecto
- `/root/.openclaw/workspace/legal-monitor/`

### Fuente de Cámara de Comercio
- PostgreSQL (`contacts`)
- conexión por `DATABASE_URL`
- dump semilla disponible en `legal-monitor/bd/seed_contacts.sql.gz`

### Corridas
- `/root/.openclaw/workspace/legal-monitor/data/runs/`

### Planes / estado
- `SPRINT_1.md`
- `PROJECT_STATUS.md`
- `ACCESS_CONTROL_PLAN.md`
- `docs/CLEANUP_POLICY.md`
- `CONTEXT.md`

---

## Comandos clave
### Corrida simple
```bash
cd /root/.openclaw/workspace/legal-monitor
source .venv/bin/activate
python scripts/run_search.py \
  --fecha-inicio 2026-03-18 \
  --fecha-fin 2026-03-18 \
  --despacho-id 050013103012
```

### Corrida con enriquecimiento en PostgreSQL
```bash
cd /root/.openclaw/workspace/legal-monitor
source .venv/bin/activate
export DATABASE_URL='postgresql://legal_monitor:<PASSWORD>@localhost:5432/legal_monitor'
python scripts/run_search.py \
  --fecha-inicio 2026-03-19 \
  --fecha-fin 2026-03-20
```

### Limpieza manual
```bash
cd /root/.openclaw/workspace/legal-monitor
source .venv/bin/activate
python scripts/cleanup_runs.py --dry-run
python scripts/cleanup_runs.py
```

---

## Estado técnico actual
### Qué ya está resuelto
- consulta automatizada al portal
- descarga de PDFs
- parseo inicial robusto
- matcher funcional
- validación multi-muestra
- enriquecimiento por demandado
- exportes operativos
- corrida end-to-end
- limpieza programada

### Qué sigue pendiente o mejorable
- endurecer aún más edge cases del parser
- mejorar ciertos nombres contaminados por layouts raros
- mejorar trazabilidad / reporting final
- integrar fase de borrador Gmail como último step comercial
- definir arquitectura multi-tenant / roles / seguridad para venta a bufetes

---

## Resultados y validaciones importantes
### Validación multi-despacho
Se validó un lote amplio sobre los 22 despachos del alcance. Resultado relevante:
- 22 despachos consultados
- 15+ con planilla procesable (en corridas iniciales)
- en validación amplia posterior:
  - 22 despachos revisados
  - 16 con publicaciones
  - 14 PDFs principales parseados
  - 180 filas en ese lote de benchmark
  - `revision_manual` bajó de 20 a 6 tras endurecimiento

### Ajustes críticos ya hechos
Se redujo ruido en despachos problemáticos:
- Juzgado 003: `3 -> 0`
- Juzgado 013: `4 -> 1`
- Juzgado 021: `2 -> 0`

### Corrida amplia con enriquecimiento
Para el rango `2026-03-17` a `2026-03-20`:
- 22 despachos consultados
- 85 publicaciones encontradas
- 84 PDFs procesados
- 1030 registros extraídos
- 481 registros relevantes
- 90 registros relevantes con email en la fuente externa de contactos (hoy migrada a PostgreSQL)

---

## Convenciones de salida enriquecida
El enriquecimiento se hace **solo por demandado**.

Campos agregados:
- `match_db`
- `email_db`
- `source_labels`
- `emails_encontrados`
- `match_total`

La semántica es:
- `email_db` = email(s) encontrados en PostgreSQL
- `source_labels` = etiquetas de origen presentes en `contacts.source_label`

---

## Política de limpieza
### Se conserva
- `exports/`
- `run_result.json`
- `run_payload.json`
- `input/`

### Se borra después de 24h
- `data/runs/*/pdfs/`
- `data/runs/*/diagnostics/`
- `data/raw/*`

### Cron instalado
```bash
17 3 * * * cd /root/.openclaw/workspace/legal-monitor && . .venv/bin/activate && python scripts/cleanup_runs.py >> /root/.openclaw/workspace/legal-monitor/logs/cleanup.log 2>&1
```

---

## Visión comercial actual
### Plan Básico
- consulta por fechas/despacho
- extracción de casos relevantes
- exportes
- revisión manual básica

### Plan Estándar
- todo lo del Básico
- enriquecimiento por Cámara de Comercio
- borradores Gmail
- ejecución programada del pipeline

### Plan Premium
- todo lo del Estándar
- control de acceso por roles
- tenant por cliente
- personalización
- soporte prioritario

---

## Seguridad / venta a bufetes
### Recomendación estructural
No venderlo como “bot abierto con acceso”.
Venderlo como producto cerrado.

### Principio clave
Primera barrera en OpenClaw/canal:
- usuario no autorizado → no entra
- idealmente → no respuesta

### Después
Segunda barrera en el agente:
- validación de identidad
- validación de rol
- validación de tenant

### Documento relacionado
- `ACCESS_CONTROL_PLAN.md`

---

## Reglas operativas del usuario (importantísimas)
### 1. Evitar respuestas duplicadas
Si hay mensajes en cola o eventos solapados:
- responder una sola vez, de forma consolidada

### 2. Regla de primer fallo
Si algo falla en el primer intento:
- parar
- explicar qué falló
- decir qué se intentaría después
- pedir confirmación antes de reintentar

### 3. Sensibilidad a costo
Evitar bucles autónomos de debugging que gasten presupuesto sin aprobación.

---

## Qué debería hacerse después
Orden recomendado:
1. cerrar fase de borrador Gmail
2. pulir algunos edge cases del parser
3. terminar documentos comerciales / seguridad
4. definir control de acceso por canal (Telegram / WhatsApp)
5. preparar operación multi-tenant para clientes

---

## Estado resumido
### Hecho
- portal
- scraper
- parser
- matcher
- enriquecimiento
- exportación
- corrida end-to-end
- limpieza automática

### En progreso
- producto comercializable multi-tenant
- seguridad / roles / permisos
- último step de borradores Gmail

### Pendiente
- acceso por cliente y canal
- planes de producto cerrados formalizados
- endurecimiento final para venta
