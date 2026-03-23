# ACCESS_CONTROL_PLAN.md — Seguridad, roles y arquitectura para vender `legal-monitor`

## Objetivo
Diseñar la capa de seguridad y control de acceso para comercializar `legal-monitor` a bufetes de abogados, de forma que los clientes solo puedan hacer consultas autorizadas dentro del producto, sin acceso a administración, scripts, archivos internos o funciones de desarrollo.

---

# Entregables a construir

## 1. Política formal del producto
Crear un documento `.md` que defina:
- alcance funcional permitido para clientes
- acciones prohibidas
- límites del agente
- política de datos
- política de exportación
- política de auditoría
- política de retención y limpieza

### Nombre sugerido
- `PRODUCT_SECURITY_POLICY.md`

### Resultado esperado
Documento listo para:
- alinear equipo interno
- mostrar a cliente si hace falta
- usar como base de configuración real

---

## 2. Matriz de roles y permisos
Diseñar una matriz clara que responda:
- quién puede hacer qué
- qué ve cada rol
- qué herramientas están permitidas por rol

### Roles mínimos sugeridos
- `platform_admin`
- `client_admin`
- `client_operator`
- `client_reviewer`
- `client_readonly`

### Permisos a mapear
- consultar casos
- consultar por fechas
- consultar por despachos
- exportar CSV/JSON
- ver revisión manual
- correr pipeline dentro del alcance permitido
- ver resultados enriquecidos
- subir bases
- editar reglas
- administrar cron
- administrar configuración
- ver logs internos
- ejecutar mantenimiento

### Nombre sugerido
- `ROLES_PERMISSIONS_MATRIX.md`

### Resultado esperado
Tabla o lista estructurada con:
- rol
- permisos permitidos
- permisos prohibidos
- alcance de datos

---

## 3. Propuesta de arquitectura tenant / admin / cliente
Diseñar cómo separar:
- administración interna
- clientes
- datos por cliente
- sesiones por cliente
- resultados por cliente

### Objetivo
Evitar mezcla de:
- datos
- consultas
- historiales
- configuraciones
- exports

### Componentes a definir
- tenant
- workspace lógico por tenant
- datasets por tenant
- outputs por tenant
- identidad del usuario
- canal de mensajería
- rol del usuario
- perímetro del agente cliente
- perímetro del agente admin

### Nombre sugerido
- `TENANT_ARCHITECTURE.md`

### Resultado esperado
Documento con propuesta de separación lógica, incluyendo:
- capa admin interna
- capa producto cliente
- aislamiento por bufete
- recomendaciones de despliegue

---

## 4. Modelo de usuarios, roles y permisos para Telegram y WhatsApp
Diseñar cómo representar identidades de usuario según canal.

### Telegram
Usar como identidad principal:
- `telegram:<user_id>`

Opcionalmente guardar:
- username
- nombre visible
- chat_id

### WhatsApp
Usar como identidad principal:
- `whatsapp:+<numero>`

Opcionalmente guardar:
- nombre visible
- proveedor
- identificador interno del proveedor

### Modelo sugerido por usuario
Campos mínimos:
- `channel`
- `principal`
- `display_name`
- `tenant_id`
- `role`
- `status`
- `allowed_actions`
- `allowed_scope`
- `created_at`
- `updated_at`

### Nombre sugerido
- `IDENTITY_AND_AUTH_MODEL.md`

### Resultado esperado
Documento con ejemplos concretos de cómo modelar:
- admins internos
- usuarios cliente
- usuarios solo lectura
- autorización por tenant
- autorización por canal

---

# Principios de diseño

## Principio 1 — Cliente no es admin
El cliente no debe poder:
- ejecutar comandos
- tocar archivos
- cambiar reglas
- ver rutas internas
- acceder a mantenimiento
- mezclar tenants

## Principio 2 — Producto cerrado
El cliente solo debe poder:
- consultar
- filtrar
- exportar
- revisar casos
- correr búsquedas dentro del alcance contratado

## Principio 3 — Aislamiento por tenant
Cada bufete debe tener:
- sus propios resultados
- su propia configuración
- su propia base enriquecida
- sus propios usuarios
- su propia política de retención si aplica

## Principio 4 — Identidad del canal = identidad de acceso
- Telegram → `user_id`
- WhatsApp → número

## Principio 5 — Rol + tenant + canal
No basta con saber quién es el usuario.
También hay que saber:
- a qué tenant pertenece
- qué rol tiene
- qué acciones puede ejecutar

---

# Orden de trabajo recomendado

## Fase A — Definir la política
1. redactar `PRODUCT_SECURITY_POLICY.md`
2. validar alcance permitido/prohibido
3. definir límites del agente cliente

## Fase B — Diseñar roles
1. definir roles mínimos
2. definir permisos por rol
3. redactar `ROLES_PERMISSIONS_MATRIX.md`

## Fase C — Diseñar arquitectura tenant
1. definir separación admin / cliente
2. definir aislamiento por bufete
3. redactar `TENANT_ARCHITECTURE.md`

## Fase D — Diseñar modelo de identidad
1. modelar Telegram
2. modelar WhatsApp
3. mapear usuario → tenant → rol
4. redactar `IDENTITY_AND_AUTH_MODEL.md`

## Fase E — Bajar a configuración real
1. decidir dónde se almacenan usuarios/roles
2. decidir cómo se valida autorización
3. decidir qué agente o prompt usa cada rol
4. definir estrategia de despliegue

---

# Preguntas que este plan debe resolver

## Sobre el producto
- ¿Qué puede pedir exactamente el cliente?
- ¿Qué no puede pedir nunca?
- ¿Qué se responde y qué se bloquea?

## Sobre seguridad
- ¿Cómo se identifica al usuario?
- ¿Cómo se sabe a qué tenant pertenece?
- ¿Cómo se evita mezcla entre bufetes?
- ¿Cómo se separa el modo admin del modo cliente?

## Sobre operación
- ¿Dónde se guardan resultados por cliente?
- ¿Qué logs se conservan?
- ¿Quién puede exportar?
- ¿Quién puede ver revisión manual?

---

# Recomendación final

La implementación debe construirse así:

## Primero
- política del producto
- primera barrera de acceso en OpenClaw/canal
- roles
- permisos

## Después
- arquitectura multi-tenant
- modelo de identidad Telegram/WhatsApp

## Finalmente
- bajar eso a configuración real del sistema

No al revés.

---

# Resultado esperado del plan completo

Al terminar este trabajo deben existir 4 documentos listos:
- `PRODUCT_SECURITY_POLICY.md`
- `ROLES_PERMISSIONS_MATRIX.md`
- `TENANT_ARCHITECTURE.md`
- `IDENTITY_AND_AUTH_MODEL.md`

Y con ellos deberían poder decidir cómo vender el producto sin abrir acceso peligroso a clientes.
