# Portal Contract — Publicaciones Procesales

## Estado
- [x] Descubrimiento inicial completado por inspección HTTP/HTML
- [ ] Validación con navegador automatizado visible (opcional en Sprint 1)

## URL base
- `https://publicacionesprocesales.ramajudicial.gov.co/`

## Namespace del portlet
- `_co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE_BIyXQFHVaYaq_`

## Filtros detectados
Selectores HTML encontrados en la página principal:
- `#departamento`
- `#municipio`
- `#entidad`
- `#especialidad`
- `#despacho`
- `#_co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE_BIyXQFHVaYaq_fechaInicio`
- `#_co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE_BIyXQFHVaYaq_fechaFin`
- `#buscar`

## Flujo real de filtros
El portal usa filtros encadenados con llamadas AJAX/JSON.

Orden confirmado:
1. Departamento
2. Municipio
3. Entidad
4. Especialidad
5. Despacho
6. Fecha inicio / fecha fin
7. Buscar

## Endpoint AJAX de filtros
El JavaScript del portal expone la función `cargarOpciones(tipo, idFiltro)`.

### URL base AJAX
`https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio?p_p_id=co_com_avanti_efectosProcesales_PublicacionesEfectosProcesalesPortletV2_INSTANCE_BIyXQFHVaYaq&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_cacheability=cacheLevelPage?`

### Parámetros observados
- `{namespace}tipoFiltro`
- `{namespace}idFiltro`
- `{namespace}id`

### Headers necesarios para obtener JSON limpio
- `X-Requested-With: XMLHttpRequest`
- `Accept: application/json, text/javascript, */*; q=0.01`

## Secuencia funcional validada para Medellín civil circuito
Con una misma sesión HTTP:
1. `tipoFiltro=departamento`, `idFiltro=05`, `id=178845807`
2. `tipoFiltro=municipio`, `idFiltro=05001`
3. `tipoFiltro=entidad`, `idFiltro=31`, `id=178845827`
4. `tipoFiltro=especialidad`, `idFiltro=03`, `id=178845875`

## Hallazgos de cascada
- `departamento=05` devuelve municipios de Antioquia
- `municipio=05001` devuelve despachos de Medellín
- `entidad=31` y `especialidad=03` afinan el universo de despachos
- En una sesión limpia, la secuencia completa devuelve **22 despachos** de `JUZGADO NNN CIVIL DEL CIRCUITO DE MEDELLÍN`

## Valores relevantes detectados
### Departamento
- Antioquia: `value=05`, `data-id=178845807`

### Municipio
- Medellín: `id=05001`

### Entidad
- Juzgado de Circuito: `value=31`, `data-id=178845827`

### Especialidad
- Civil: `value=03`, `data-id=178845875`

## Búsqueda principal
El botón `#buscar` arma una URL GET a:

`https://publicacionesprocesales.ramajudicial.gov.co/web/publicaciones-procesales/inicio?...&{namespace}action=busqueda`

### Parámetros observados en búsqueda
- `{namespace}fechaInicio`
- `{namespace}fechaFin`
- `{namespace}idDepto`
- `{namespace}idMuni`
- `{namespace}idEntidad`
- `{namespace}idEspecialidad`
- `{namespace}idDespacho` (opcional)
- `{namespace}verTotales`
- `{namespace}idDeptoIdCategory`

## Paginación del portal
Confirmada.
La respuesta HTML de búsqueda incluye parámetros como:
- `{namespace}cur`
- `{namespace}delta`
- `{namespace}resetCur=false`

Por defecto se observaron `10 resultados por página`.

## Estructura de resultados
Cada publicación aparece como bloque HTML con:
- título enlazado
- categorías visibles
- fecha de publicación
- botón `Ver detalle`

Campos visibles observados:
- Tipo de publicación
- Departamento
- Municipio
- Entidad
- Especialidad
- Despacho
- Fecha de publicación

## Resolución de detalle
El resultado no siempre expone el PDF directo en la lista.
Se detectó una URL de detalle con `jspPage=/META-INF/resources/detail.jsp` y `articleId=...`.

Ejemplo de patrón:
- `...&{namespace}jspPage=%2FMETA-INF%2Fresources%2Fdetail.jsp&{namespace}articleId=207248707...`

## Resolución del PDF
En la página de detalle se detectaron enlaces descargables tipo:
- `/documents/{groupId}/{articleId}/{filename}/{uuid}?t=...`
- `/c/document_library/get_file?uuid={uuid}&groupId={groupId}`

El formato `/c/document_library/get_file?...` es el más conveniente para descarga estable.

## Ejemplo real observado
Publicación:
- `Notificación por Estado No.041 de 19 de marzo de 2026`
- Despacho: `050013103012 - JUZGADO 012 CIVIL DEL CIRCUITO DE MEDELLÍN`
- Fecha de publicación visible: `2026-03-18`

Archivos encontrados en detalle:
- `Planilla Estados Nro. 041.pdf`
- `AdmiteServidumbre__2026_00069 (1).pdf`
- `AutoAdmite CARTA ROGATORIA 2026-00119.pdf`
- `AutoInadmiteVerbalRCC 2026-00076.pdf`
- otros autos/documentos del mismo detalle

## Riesgos detectados
- La lista principal puede no exponer el PDF final sin entrar a detalle
- Un detalle puede contener múltiples archivos, no solo la planilla principal
- La fecha visible de la publicación y el nombre del PDF pueden diferir (p.ej. publicación del 18 con documento que dice 19)
- El flujo AJAX depende de mantener sesión HTTP consistente

## Decisiones de implementación derivadas
1. Preferir requests HTTP + sesión para descubrimiento/canonización
2. Usar búsqueda GET reproducible para resultados
3. Entrar a detalle cuando sea necesario para obtener enlaces `get_file`
4. Descargar y priorizar PDFs de planilla/estado antes que anexos secundarios
5. Mantener soporte de paginación del portal desde el primer scraper
