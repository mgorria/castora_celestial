# Control Castora

Sistema de bots de Telegram para una narrativa personal.

El proyecto ejecuta dos bots en el mismo proceso:

- **Oficina Castori**, el bot visible para Sandra.
- **Centralita Magica**, el bot privado desde el que se envian mensajes y se reciben respuestas.

La estructura esta preparada para anadir mas animales en el futuro mediante el diccionario `ANIMALS` de `main.py`.

## Requisitos

- Python 3.11 o superior.
- Dos tokens de BotFather:
  - `TOKEN_CASTORI`
  - `TOKEN_CENTRALITA`
- Tu chat id personal de Telegram:
  - `MI_CHAT_ID`
  - `CASTORI_CHAT_ID` si ya se conoce el chat id de Sandra.

## Configuracion local

Crea un archivo `.env` en la raiz del proyecto con este contenido:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=
LOG_LEVEL=INFO
DATA_FILE=data.json
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
/historial castori
/historial castori 20
```

Las respuestas que Sandra envie a Oficina Castori se copiaran automaticamente a tu chat privado con Centralita.
El historial guarda los ultimos mensajes de cada animal en `data.json`.

## Railway

En Railway, conecta el repositorio de GitHub y configura estas variables:

```env
TOKEN_CASTORI=token_real_de_oficina_castori
TOKEN_CENTRALITA=token_real_de_centralita_magica
MI_CHAT_ID=tu_chat_id
CASTORI_CHAT_ID=chat_id_de_sandra
LOG_LEVEL=INFO
DATA_FILE=data.json
MAX_HISTORY_PER_ANIMAL=50
```

Si `CASTORI_CHAT_ID` esta configurado, el bot lo usara directamente aunque `data.json` no exista todavia en Railway.

Railway usara el `Procfile`:

```Procfile
worker: python main.py
```

## Nota de seguridad

No subas nunca el archivo `.env` ni `data.json` al repositorio. Ya estan incluidos en `.gitignore`.
