# Control Castora

Sistema de bots de Telegram para una narrativa personal.

El proyecto ejecuta varios bots en el mismo proceso:

- **Oficina Castori**, el bot visible para Sandra.
- **Mimosuga**, una tortuguita muy mayor y entrañable, figura de abuela para Sandra.
- **Centralita Magica**, el bot privado desde el que se envian mensajes y se reciben respuestas.

La estructura esta preparada para anadir mas animales en el futuro mediante el diccionario `ANIMALS` de `main.py`.

## Requisitos

- Python 3.11 o superior.
- Tokens de BotFather:
  - `TOKEN_CASTORI`
  - `TOKEN_MIMOSUGA`
  - `TOKEN_CENTRALITA`
- Tu chat id personal de Telegram:
  - `MI_CHAT_ID`
  - `CASTORI_CHAT_ID` si ya se conoce el chat id de Sandra.
  - `MIMOSUGA_CHAT_ID` si ya se conoce el chat id de Sandra para Mimosuga.

## Configuracion local

Crea un archivo `.env` en la raiz del proyecto con este contenido:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_MIMOSUGA=token_real_de_mimosuga
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=
MIMOSUGA_CHAT_ID=
LOG_LEVEL=INFO
DATA_FILE=data.json
MAX_HISTORY_PER_ANIMAL=50
```

Instala dependencias:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Arranca el sistema:

```powershell
.\start.ps1
```

## Uso

Primero Sandra debe abrir el bot **Oficina Castori** y enviar `/start`.

En ese momento el proyecto guarda automaticamente su `chat_id` en `data.json`.

Desde tu Telegram, abre **Centralita Magica** y usa:

```text
/status
/castori texto que quieres enviar
/mimosuga texto que quieres enviar
/historial castori
/historial mimosuga
/historial castori 20
/programar mimosuga lunes 09:00 Que tengas buena semana, patita.
/programar mimosuga 21/06/2026 16:00 Tengo algo que contarte, sol mio.
/programados
/cancelar id_de_programacion
/pausar_programas
/reanudar_programas
```

Las respuestas que Sandra envie a Oficina Castori se copiaran automaticamente a tu chat privado con Centralita.
El historial guarda los ultimos mensajes de cada animal en `data.json`.
Los mensajes programados pueden ser semanales o de una fecha exacta, se revisan periodicamente y se envian en la zona horaria configurada.
Si algo raro ocurre, `/pausar_programas` detiene los envios programados hasta usar `/reanudar_programas`.

## Cuentos y lore

Mimosuga puede ofrecer un cuento diario con:

```text
/cuento
```

El flujo es:

1. Mimosuga comprueba si Patita ya recibio cuento hoy.
2. Si no lo recibio, genera dos opciones basadas en `lore/resumen-para-ia.md`.
3. Patita elige una opcion con botones.
4. Mimosuga genera y envia el cuento completo.
5. Solo despues de enviarlo se consume el limite diario.
6. La historia queda guardada en PostgreSQL con estado `pending`.

Comandos privados de administrador en **Centralita Magica**:

```text
/admin_ultimos
/admin_ver ID
/admin_aprobar ID
/admin_descartar ID
/admin_canon ID
/admin_lore
/admin_memoria_cuentos
/admin_cuento_prueba mimosuga
```

El lore editable vive en:

```text
lore/resumen-para-ia.md
lore/reglas-de-tono.md
lore/personajes/
lore/historias/
```

## Railway

En Railway, conecta el repositorio de GitHub y configura estas variables:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_MIMOSUGA=token_real_de_mimosuga
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=chat_id_de_sandra
MIMOSUGA_CHAT_ID=chat_id_de_sandra_para_mimosuga
LOG_LEVEL=INFO
DATA_FILE=data.json
MAX_HISTORY_PER_ANIMAL=50
APP_TIMEZONE=Europe/Madrid
SCHEDULER_POLL_SECONDS=30
STARTUP_DELAY_SECONDS=8
DATABASE_URL=postgresql://...
OPENAI_API_KEY=tu_api_key_openai
OPENAI_MODEL=gpt-5.2
TELEGRAM_ADMIN_ID=tu_chat_id
SANDRA_TELEGRAM_ID=chat_id_de_sandra
PENDING_STORIES_DIR=/app/data/lore/historias/pendientes
RECENT_STORY_MEMORY_PATH=/app/data/lore/historias/memoria-reciente.md
```

Si `CASTORI_CHAT_ID` esta configurado, el bot lo usara directamente aunque `data.json` no exista todavia en Railway.

Para persistencia en Railway, crea un Volume montado en `/app/data` y configura:

```env
DATA_FILE=/app/data/data.json
```

Si Railway expone `RAILWAY_VOLUME_MOUNT_PATH`, el bot tambien puede usar automaticamente `data.json` dentro del volumen.

Railway usara el `Procfile`:

```Procfile
worker: python main.py
```

Al arrancar, el bot crea automaticamente las tablas necesarias si `DATABASE_URL` esta configurada:

- `users`
- `stories`
- `daily_limits`
- `story_offers`

## Nota de seguridad

No subas nunca el archivo `.env` ni `data.json` al repositorio. Ya estan incluidos en `.gitignore`.
