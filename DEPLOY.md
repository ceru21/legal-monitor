# Deployment en VPS

## Lo que ya existe localmente

| Componente | Estado |
|---|---|
| Scraper + pipeline end-to-end | ✅ Funcional |
| PostgreSQL vía Docker Compose | ✅ Configurado |
| `db/` — modelos, schema, repositorio, import_contacts | ✅ Listo |
| `.env.example` con valores de desarrollo | ✅ Documentado |
| `--no-db` flag para correr sin BD | ✅ Disponible |
| Puerto 5432 restringido a `127.0.0.1` | ✅ Hardened |
| `POSTGRES_PASSWORD` obligatorio (sin default) | ✅ Hardened |

---

## Requisitos del VPS

- Ubuntu 22.04 / Debian 12 (o equivalente)
- Docker Engine + Docker Compose plugin
- Python 3.11+
- Git
- Usuario no-root con acceso a Docker (`sudo usermod -aG docker $USER`)

---

## Pasos de deployment

### 1. Conectarse al VPS

```bash
ssh usuario@<IP_VPS>
```

### 2. Instalar dependencias del sistema

```bash
# Docker (si no está instalado)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker

# Python 3.11+
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip git
```

### 3. Clonar el repositorio

```bash
cd /opt   # o ~/apps, donde prefieras
git clone <URL_DEL_REPO> legal-monitor
cd legal-monitor
```

### 4. Crear el `.env` con secretos de producción

**Nunca copies el `.env.example` literal en producción — usa una contraseña fuerte.**

```bash
cp .env.example .env
nano .env   # o vim .env
```

Contenido mínimo para producción:

```env
DATABASE_URL=postgresql://legal_monitor:<PASSWORD_FUERTE>@127.0.0.1:5432/legal_monitor
POSTGRES_PASSWORD=<PASSWORD_FUERTE>
```

> Usa `openssl rand -hex 32` para generar una contraseña segura.

Restringir permisos del archivo:

```bash
chmod 600 .env
```

### 5. Levantar PostgreSQL

```bash
docker compose up -d
docker compose ps   # esperar (healthy)
```

### 6. Crear entorno virtual e instalar dependencias

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 7. Inicializar el schema

```bash
python -m db.init_schema
```

### 8. (Opcional) Importar contactos de Cámara de Comercio

```bash
python -m db.import_contacts --file /ruta/al/archivo.TXT --label colombia_2026
```

### 9. Verificar conexión end-to-end

```bash
python -c "from db import get_session; print('DB OK')"
```

---

## Ejecutar el pipeline

### Una sola corrida manual

```bash
source .venv/bin/activate
python scripts/run_search.py \
  --fecha-inicio 2024-01-01 \
  --fecha-fin 2024-01-31
```

Los resultados quedan en `data/runs/<run_label>/`.

### Cron — corrida automática diaria

Editar crontab del usuario:

```bash
crontab -e
```

Agregar (ajusta hora según tu zona):

```cron
# Corre el pipeline cada día a las 6am (hora del servidor)
0 6 * * * /opt/legal-monitor/.venv/bin/python /opt/legal-monitor/scripts/run_search.py \
  --fecha-inicio $(date -d "yesterday" +\%Y-\%m-\%d) \
  --fecha-fin $(date +\%Y-\%m-\%d) \
  >> /opt/legal-monitor/logs/pipeline.log 2>&1
```

Crear el directorio de logs:

```bash
mkdir -p /opt/legal-monitor/logs
```

---

## Actualizar el código

```bash
cd /opt/legal-monitor
git pull
source .venv/bin/activate
pip install -r requirements.txt   # si hubo cambios en dependencias
# Si hubo cambios de schema:
python -m db.init_schema
```

---

## Secretos — resumen de variables de entorno

| Variable | Requerida | Descripción |
|---|---|---|
| `DATABASE_URL` | Sí | Connection string completo de Postgres |
| `POSTGRES_PASSWORD` | Sí | Contraseña de Postgres (usada por docker-compose) |
| `DB_SSLMODE` | No | SSL para la conexión (`require` / `verify-full`) |

---

## Backup de la base de datos

```bash
docker exec legal_monitor_db pg_dump -U legal_monitor legal_monitor \
  | gzip > /backups/legal_monitor_$(date +%Y%m%d).sql.gz
```

Agregar al cron para backup diario:

```cron
30 5 * * * docker exec legal_monitor_db pg_dump -U legal_monitor legal_monitor \
  | gzip > /backups/legal_monitor_$(date +\%Y\%m\%d).sql.gz
```

---

## Checklist de verificación post-deploy

- [ ] `docker compose ps` muestra `(healthy)`
- [ ] `python -c "from db import get_session; print('OK')"` sin error
- [ ] `python -m db.init_schema` sin error
- [ ] Corrida manual del pipeline termina con `run_result.json` generado
- [ ] Archivo `.env` tiene permisos `600`
- [ ] `.env` NO está en git (`git status` no lo muestra)
- [ ] Cron configurado y primer log generado al día siguiente
