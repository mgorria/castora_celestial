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
/status
```

Las respuestas que Sandra envie a Oficina Castori se copiaran automaticamente a tu chat privado con Centralita.
El historial guarda los ultimos mensajes de cada animal en `data.json`.
Los mensajes programados pueden ser semanales o de una fecha exacta, se revisan periodicamente y se envian en la zona horaria configurada.
Si algo raro ocurre, `/pausar_programas` detiene los envios programados hasta usar `/reanudar_programas`.
`/status` muestra el estado general: bots vinculados, Railway/worker, base de datos,
OpenAI, programaciones, respuestas suaves de Mimosuga, cuentos y comandos utiles.

## Cuentos y lore

Mimosuga puede ofrecer un cuento diario con:

```text
/cuento
/cuento historia de Caparantonio
/cuento algo sobre una carta antigua
```

El flujo es:

1. Mimosuga comprueba si Patita ya recibio cuento hoy.
2. Si no lo recibio, genera dos opciones basadas en `lore/resumen-para-ia.md`.
   Si Patita escribe algo despues de `/cuento`, lo usa como tema orientativo.
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
/mimosuga_auto status
/mimosuga_auto on
/mimosuga_auto auto
/mimosuga_auto revision
/mimosuga_auto off
```

El lore editable vive en:

```text
lore/resumen-para-ia.md
lore/continuidad-canonica.md
lore/reglas-de-tono.md
lore/personajes/
lore/historias/
```

`lore/continuidad-canonica.md` sirve para fijar hechos que solo deben ocurrir una vez,
como el primer encuentro de Mimosuga y Caparantonio. Cuando una historia de origen te
guste, resume ahi la version canonica para que futuras historias no la contradigan.

## Respuestas suaves de Mimosuga

Mimosuga puede preparar borradores automaticos de respuesta cuando Patita le escriba.
Puede funcionar en modo revision o en modo automatico. En modo revision, el administrador
recibe la propuesta en **Centralita Magica** y decide con botones si la envia o la descarta.
En modo automatico, Mimosuga envia sola las respuestas que la IA considera charla ligera;
si el mensaje parece delicado, importante o ambiguo, avisa al administrador y no envia nada.

Comandos privados:

```text
/mimosuga_auto on
/mimosuga_auto auto
/mimosuga_auto revision
/mimosuga_auto off
/mimosuga_auto status
```

`/mimosuga_auto on` activa el modo revision. Para activar envio automatico hay que usar
explicitamente `/mimosuga_auto auto`.

Cuando esta encendido, cada mensaje textual que llegue a Mimosuga genera una propuesta
breve si la IA lo considera una charla ligera. Para que no responda frase por frase,
el bot espera unos segundos antes de redactar: si Patita envia varios mensajes seguidos,
los agrupa y prepara una sola respuesta para todo el bloque. Si el mensaje parece delicado
o no trivial, la Centralita avisa al administrador y no propone una respuesta automatica.

La espera de agrupacion se puede ajustar con:

```env
AUTO_REPLY_IDLE_SECONDS=90
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
AUTO_REPLY_IDLE_SECONDS=90
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
- `auto_reply_drafts`

## Nota de seguridad

No subas nunca el archivo `.env` ni `data.json` al repositorio. Ya estan incluidos en `.gitignore`.
