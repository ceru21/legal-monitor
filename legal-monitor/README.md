# legal-monitor

Monitoreo de publicaciones procesales de la Rama Judicial.

## Objetivo
Construir un pipeline verificable para:
- descubrir despachos objetivo
- consultar publicaciones por fecha
- resolver y descargar PDFs
- extraer datos útiles del contenido
- aplicar matching inicial
- exportar resultados auditables

## Estado actual
El proyecto está en **Sprint 1**. Ya existe descubrimiento técnico del portal, lista de despachos de referencia, scraper inicial y evidencia real de al menos una descarga de PDF.

Ver:
- `SPRINT_1.md`
- `STATUS_FOR_CESAR.md`
- `references/portal-contract.md`

## Estructura
- `config/`: configuración del pipeline y patrones
- `references/`: documentación técnica del portal y catálogos de apoyo
- `scripts/`: código fuente del scraper y utilidades
- `tests/`: fixtures y ground truth inicial
- `data/`: artefactos generados en ejecución (**ignorado en git**)

## Dependencias actuales
### Python
El proyecto tiene componentes en Python para scraper/modelos/utilidades.

### Node
Se añadió soporte local con Node para destrabar parsing de PDF en entornos donde Python no tenga las dependencias necesarias.

Instalar dependencias Node:

```bash
npm install
```

## Archivos clave
- `scripts/scraper_portal.py`
- `scripts/models.py`
- `scripts/utils.py`
- `config/target_patterns.yaml`
- `references/despachos_medellin_civil_circuito.json`
- `references/portal-contract.md`

## Git / publicación
Este repositorio está preparado para subirse sin:
- `node_modules/`
- `.venv/`
- `__pycache__/`
- `data/`
- PDFs y artefactos locales

## Próximo objetivo técnico
Cerrar el flujo mínimo de punta a punta:
1. descarga real de PDFs
2. parser inicial funcional
3. extracción de filas útiles
4. exportación JSON/CSV
