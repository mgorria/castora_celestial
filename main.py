import asyncio
import json
import logging
import os
import socket
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


load_dotenv()

logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=os.getenv("LOG_LEVEL", "INFO"),
)
logger = logging.getLogger("control-castora")
logging.getLogger("httpx").setLevel(logging.WARNING)

DATA_FILE = Path(os.getenv("DATA_FILE", "data.json"))

TOKEN_CASTORI = os.getenv("TOKEN_CASTORI")
TOKEN_CENTRALITA = os.getenv("TOKEN_CENTRALITA")
MI_CHAT_ID = os.getenv("MI_CHAT_ID")

ANIMALS: dict[str, dict[str, str]] = {
    "castori": {
        "display_name": "Oficina Castori",
        "token_env": "TOKEN_CASTORI",
        "chat_id_env": "CASTORI_CHAT_ID",
        "partner_key": "castori_partner_chat_id",
        "central_command": "castori",
    }
}

animal_apps: dict[str, Application] = {}
centralita_app: Application | None = None
lock_socket: socket.socket | None = None


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def owner_chat_id() -> int:
    if not MI_CHAT_ID:
        raise RuntimeError("Falta la variable de entorno MI_CHAT_ID")
    return int(MI_CHAT_ID)


def load_data() -> dict[str, Any]:
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.exception("No se pudo leer %s; se usara un estado vacio", DATA_FILE)
        return {}


def save_data(data: dict[str, Any]) -> None:
    DATA_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_partner_chat_id(animal_key: str) -> int | None:
    env_chat_id = os.getenv(ANIMALS[animal_key]["chat_id_env"])
    if env_chat_id:
        return int(env_chat_id)

    data = load_data()
    partner_key = ANIMALS[animal_key]["partner_key"]
    value = data.get(partner_key)
    return int(value) if value else None


def set_partner_chat_id(animal_key: str, chat_id: int) -> None:
    data = load_data()
    partner_key = ANIMALS[animal_key]["partner_key"]
    data[partner_key] = chat_id
    save_data(data)


def is_owner(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == owner_chat_id())


def acquire_single_instance_lock() -> None:
    global lock_socket

    port = int(os.getenv("LOCAL_LOCK_PORT", "47417"))
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
    except OSError as exc:
        raise RuntimeError(
            "Ya hay una copia de Control Castora en marcha. "
            "Cierra la otra ventana o pulsa Ctrl+C alli antes de arrancar otra."
        ) from exc
    lock_socket = sock


async def central_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    await update.effective_chat.send_message(
        "Centralita Magica operativa.\n\n"
        "Comandos disponibles:\n"
        "/castori <mensaje>\n"
        "/status"
    )


async def central_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    lines = ["Estado de la Centralita Magica:"]
    for animal_key, animal in ANIMALS.items():
        partner_chat_id = get_partner_chat_id(animal_key)
        status = "vinculado" if partner_chat_id else "pendiente de /start"
        lines.append(f"- {animal['display_name']}: {status}")

    await update.effective_chat.send_message("\n".join(lines))


async def central_castori(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_as_animal("castori", update, context)


async def send_as_animal(
    animal_key: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat or not update.message or not is_owner(update):
        return

    command = ANIMALS[animal_key]["central_command"]
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_chat.send_message(f"Uso: /{command} <mensaje>")
        return

    partner_chat_id = get_partner_chat_id(animal_key)
    if not partner_chat_id:
        await update.effective_chat.send_message(
            f"Todavia no tengo el chat_id de {ANIMALS[animal_key]['display_name']}. "
            "Sandra debe iniciar ese bot con /start una primera vez."
        )
        return

    animal_app = animal_apps[animal_key]
    await animal_app.bot.send_chat_action(partner_chat_id, ChatAction.TYPING)
    await animal_app.bot.send_message(chat_id=partner_chat_id, text=text)
    await update.effective_chat.send_message(
        f"Enviado desde {ANIMALS[animal_key]['display_name']}."
    )


async def animal_start(
    animal_key: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    set_partner_chat_id(animal_key, chat_id)

    await update.effective_chat.send_message(
        "La Oficina Castori acusa recibo de su comparecencia inicial. "
        "El expediente queda abierto y bajo custodia administrativa."
    )

    if not centralita_app:
        raise RuntimeError("Centralita no inicializada")

    await centralita_app.bot.send_message(
        chat_id=owner_chat_id(),
        text=(
            f"{ANIMALS[animal_key]['display_name']} ha capturado un chat_id: "
            f"{chat_id}"
        ),
    )


async def animal_message(
    animal_key: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat or not update.message:
        return

    partner_chat_id = get_partner_chat_id(animal_key)
    if update.effective_chat.id != partner_chat_id:
        await update.effective_chat.send_message(
            "La Oficina Castori no localiza expediente asociado a este acceso. "
            "Presente primero /start para su registro provisional."
        )
        return

    if not centralita_app:
        raise RuntimeError("Centralita no inicializada")

    sender = update.effective_user.full_name if update.effective_user else "Sandra"
    text = update.message.text or update.message.caption

    await centralita_app.bot.send_message(
        chat_id=owner_chat_id(),
        text=f"Respuesta recibida en {ANIMALS[animal_key]['display_name']} de {sender}:",
    )
    if text:
        await centralita_app.bot.send_message(chat_id=owner_chat_id(), text=text)
    else:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "Ha llegado un mensaje no textual. "
                "Para revisarlo, abre temporalmente el bot del animal correspondiente."
            ),
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Error gestionando update %s", update, exc_info=context.error)
    try:
        await context.bot.send_message(
            chat_id=owner_chat_id(),
            text=f"Error en bot: {context.error}",
        )
    except Exception:
        logger.exception("No se pudo notificar el error al propietario")


def build_centralita_app() -> Application:
    app = (
        ApplicationBuilder()
        .token(require_env("TOKEN_CENTRALITA"))
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(CommandHandler("start", central_start))
    app.add_handler(CommandHandler("status", central_status))
    app.add_handler(CommandHandler("castori", central_castori))
    app.add_error_handler(error_handler)
    return app


def build_animal_app(animal_key: str) -> Application:
    token = require_env(ANIMALS[animal_key]["token_env"])
    app = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )
    app.add_handler(
        CommandHandler(
            "start",
            lambda update, context: animal_start(animal_key, update, context),
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            lambda update, context: animal_message(animal_key, update, context),
        )
    )
    app.add_error_handler(error_handler)
    return app


async def start_app(app: Application) -> None:
    logger.info("Inicializando bot de Telegram")
    await app.initialize()
    await app.start()
    if not app.updater:
        raise RuntimeError("La aplicacion no tiene updater configurado")
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("%s escuchando Telegram", app.bot.name)


async def stop_app(app: Application) -> None:
    if app.updater:
        await app.updater.stop()
    await app.stop()
    await app.shutdown()


async def main() -> None:
    global centralita_app

    acquire_single_instance_lock()
    _ = owner_chat_id()
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    centralita_app = build_centralita_app()
    for animal_key in ANIMALS:
        animal_apps[animal_key] = build_animal_app(animal_key)

    apps = [centralita_app, *animal_apps.values()]
    for app in apps:
        await start_app(app)

    logger.info("Centralita y bots animales en marcha")

    try:
        await asyncio.Event().wait()
    finally:
        for app in reversed(apps):
            await stop_app(app)


if __name__ == "__main__":
    asyncio.run(main())
