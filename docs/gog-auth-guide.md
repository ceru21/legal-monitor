# Guía: Autenticar una cuenta de correo con gog

## Prerrequisitos

- `gog` instalado en el servidor
- Credenciales OAuth configuradas en `/root/.config/gogcli/credentials.json`
- Proyecto en Google Cloud Console con:
  - Gmail API, Drive API y/o Sheets API habilitadas
  - OAuth consent screen configurado (tipo External, estado Testing)
  - La cuenta a autenticar agregada como **Test user**
  - Credenciales OAuth tipo **Desktop app**

## Paso a paso

### 1. Ejecutar el comando de autenticación

```bash
GOG_KEYRING_PASSWORD="" gog auth add CORREO@gmail.com --services gmail,drive,sheets --manual
```

> Reemplaza `CORREO@gmail.com` con la cuenta que quieres autenticar.
> Ajusta `--services` según lo que necesites: `gmail`, `drive`, `sheets`, `calendar`, `contacts`, `docs`.

### 2. Copiar la URL de autorización

El comando imprimirá algo como:

```
Visit this URL to authorize:
https://accounts.google.com/o/oauth2/auth?access_type=offline&client_id=...

After authorizing, you'll be redirected to a loopback URL that won't load.
Copy the URL from your browser's address bar and paste it here.

Paste redirect URL (Enter or Ctrl-D):
```

### 3. Abrir la URL en el navegador

- Copia la URL completa que comienza con `https://accounts.google.com/o/oauth2/auth?...`
- Ábrela en tu navegador (puede ser en tu PC, no necesita ser en el servidor)
- Inicia sesión con la cuenta que estás autenticando
- Concede los permisos solicitados (Gmail, Drive, Sheets, etc.)

### 4. Copiar la URL de callback

Después de autorizar, el navegador te redirigirá a una URL como:

```
http://127.0.0.1:XXXXX/oauth2/callback?state=...&code=...&scope=...
```

**Esta página NO va a cargar** — es normal (dice "ERR_CONNECTION_REFUSED").

Copia la **URL completa** de la barra de direcciones del navegador.

### 5. Pegar la URL de callback

Vuelve a la terminal donde está corriendo `gog auth add` y pega la URL completa. Presiona Enter.

Si todo sale bien verás:

```
email       CORREO@gmail.com
services    drive,gmail,sheets
client      default
```

### 6. Verificar

```bash
GOG_KEYRING_PASSWORD="" gog auth list
```

Debería mostrar la cuenta recién autenticada con sus servicios y fecha.

## Notas importantes

- **`GOG_KEYRING_PASSWORD=""`**: Usa keyring sin contraseña. Si necesitas contraseña, cámbialo.
- **Test users**: Si la app está en modo "Testing" en Google Cloud Console, solo las cuentas agregadas como test users pueden autenticarse.
- **Tokens**: Los refresh tokens se guardan en `/root/.config/gogcli/keyring/`.
- **Expiración**: Si Google revoca el token (inactividad >6 meses en apps de testing), repite el proceso.
- **Variable de entorno**: Para no repetir `--account` en cada comando, usa `export GOG_ACCOUNT=CORREO@gmail.com`.

## Ejemplo de uso después de autenticar

```bash
# Ver correos recientes
GOG_KEYRING_PASSWORD="" GOG_ACCOUNT=CORREO@gmail.com gog gmail search 'newer_than:7d' --max 10

# Crear un borrador
GOG_KEYRING_PASSWORD="" GOG_ACCOUNT=CORREO@gmail.com gog gmail draft create \
  --to destinatario@gmail.com \
  --subject "Asunto" \
  --body "Contenido del correo" \
  --force

# Listar archivos en Drive
GOG_KEYRING_PASSWORD="" GOG_ACCOUNT=CORREO@gmail.com gog drive search "name contains 'reporte'" --max 10
```
