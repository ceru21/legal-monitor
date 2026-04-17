# Checklist de setup local / VPS para PostgreSQL + seed de Cámara de Comercio

Guía marcable para dejar el entorno listo por primera vez.

---

## Requisitos previos

- [ ] Docker Desktop / Docker Engine 24+ disponible (`docker --version`)
- [ ] Docker Compose plugin 2.x disponible (`docker compose version`)
- [ ] Python 3.11+ disponible (`python3 --version`)
- [ ] Git disponible (`git --version`)

---

## 1. Clonar / ubicar el repositorio

- [ ] Entrar al proyecto correcto

```bash
git clone <URL_DEL_REPO> legal-monitor
cd legal-monitor
```

- [ ] Confirmar que existen estos archivos/rutas:
  - [ ] `docker-compose.yml`
  - [ ] `.env.example`
  - [ ] `db/`
  - [ ] `scripts/run_search.py`

---

## 2. Crear `.env`

- [ ] Copiar archivo base

```bash
cp .env.example .env
```

- [ ] Editar `.env` con credenciales fuertes de producción
- [ ] Verificar mínimo estas variables:
  - [ ] `DATABASE_URL=postgresql://legal_monitor:<PASSWORD_FUERTE>@127.0.0.1:5432/legal_monitor`
  - [ ] `POSTGRES_PASSWORD=<PASSWORD_FUERTE>`
  - [ ] `POSTGRES_USER=legal_monitor` (si aplica)
  - [ ] `POSTGRES_DB=legal_monitor` (si aplica)
- [ ] Restringir permisos del archivo

```bash
chmod 600 .env
```

> Para desarrollo local puedes usar valores simples. Para VPS/producción usa contraseñas fuertes y únicas.

---

## 3. Levantar PostgreSQL

- [ ] Iniciar contenedor

```bash
docker compose --env-file .env up -d
```

- [ ] Confirmar que quedó `healthy`

```bash
docker compose --env-file .env ps
```

- [ ] Si no está listo, esperar 15 segundos y volver a verificar

---

## 4. Restaurar la base de datos con Cámara de Comercio

### Opción A — usando el archivo en la ruta actual del workspace

- [ ] Verificar que existe el dump:
  - [ ] `/root/.openclaw/workspace/legal-monitor/legal-monitor/bd/seed_contacts.sql.gz`

- [ ] Restaurar dump en PostgreSQL

```bash
gunzip -c /root/.openclaw/workspace/legal-monitor/legal-monitor/bd/seed_contacts.sql.gz \
  | docker exec -i legal_monitor_db psql -U legal_monitor legal_monitor
```

### Opción B — mover/copiar el dump a la raíz del proyecto

- [ ] Copiar `seed_contacts.sql.gz` a la raíz del repo
- [ ] Restaurar:

```bash
gunzip -c seed_contacts.sql.gz | docker exec -i legal_monitor_db psql -U legal_monitor legal_monitor
```

### Validación posterior

- [ ] Verificar que `contacts` tiene registros

```bash
docker exec legal_monitor_db psql -U legal_monitor legal_monitor \
  -c "SELECT COUNT(*) FROM contacts;"
```

- [ ] Confirmar que el total sea mayor a 0

---

## 5. Crear entorno virtual e instalar dependencias

- [ ] Crear virtualenv
- [ ] Activarlo
- [ ] Instalar dependencias

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows

pip install -r requirements.txt
```

---

## 6. Verificar conexión app ↔ DB

- [ ] Probar conexión desde Python

```bash
python -c "from db import get_session; print('DB OK')"
```

- [ ] Confirmar que imprime `DB OK`

---

## 7. Ejecutar prueba corta del pipeline

- [ ] Correr una ejecución manual corta

```bash
python scripts/run_search.py \
  --fecha-inicio 2024-01-01 \
  --fecha-fin 2024-01-07
```

- [ ] Confirmar que genera salida en `data/runs/<run_label>/`
- [ ] Confirmar que no falla el enriquecimiento con DB

### Prueba alternativa sin DB (solo scraper)

- [ ] Ejecutar solo si quieres aislar problemas del scraper

```bash
python scripts/run_search.py \
  --fecha-inicio 2024-01-01 \
  --fecha-fin 2024-01-07 \
  --no-db
```

---

## 8. Checklist extra para VPS / producción

- [ ] Confirmar que `5432` no queda expuesto públicamente
- [ ] Confirmar permisos `600` en `.env`
- [ ] Confirmar que `.env` no está versionado en git
- [ ] Tomar backup inicial tras restaurar
- [ ] Definir estrategia de backup periódico
- [ ] Definir cron / scheduler para ejecución automática del pipeline
- [ ] Dejar logs persistentes en `logs/`

---

## Solución de problemas frecuentes

**`POSTGRES_PASSWORD is required`**
Siempre lanza docker compose con `--env-file .env`:
```bash
docker compose --env-file .env up -d
```

**`psql: error: connection refused`**
El contenedor no está listo aún. Espera y verifica con `docker compose --env-file .env ps`.

**`relation "contacts" does not exist`**
El dump no se restauró correctamente. Repite el paso 4.

**`ModuleNotFoundError`**
Asegúrate de tener el entorno virtual activado (`source .venv/bin/activate`).

---

## Apagar el entorno

```bash
docker compose --env-file .env down       # detiene el contenedor, conserva datos
docker compose --env-file .env down -v    # detiene Y borra todos los datos (reset total)
```
