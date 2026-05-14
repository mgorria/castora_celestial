import asyncio
import json
import logging
import os
import socket
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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

DEFAULT_DATA_FILE = (
    Path(os.getenv("RAILWAY_VOLUME_MOUNT_PATH")) / "data.json"
    if os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
    else Path("data.json")
)
DATA_FILE = Path(os.getenv("DATA_FILE", str(DEFAULT_DATA_FILE)))
MAX_HISTORY_PER_ANIMAL = int(os.getenv("MAX_HISTORY_PER_ANIMAL", "50"))
APP_TIMEZONE = ZoneInfo(os.getenv("APP_TIMEZONE", "Europe/Madrid"))
SCHEDULER_POLL_SECONDS = int(os.getenv("SCHEDULER_POLL_SECONDS", "30"))

WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "miércoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}
WEEKDAY_NAMES = {
    0: "lunes",
    1: "martes",
    2: "miercoles",
    3: "jueves",
    4: "viernes",
    5: "sabado",
    6: "domingo",
}

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
    },
    "mimosuga": {
        "display_name": "Mimosuga",
        "token_env": "TOKEN_MIMOSUGA",
        "chat_id_env": "MIMOSUGA_CHAT_ID",
        "partner_key": "mimosuga_partner_chat_id",
        "central_command": "mimosuga",
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


def has_seen_start(animal_key: str, chat_id: int) -> bool:
    data = load_data()
    starts = data.get("starts", {})
    return starts.get(animal_key) == chat_id


def mark_seen_start(animal_key: str, chat_id: int) -> None:
    data = load_data()
    starts = data.setdefault("starts", {})
    starts[animal_key] = chat_id
    save_data(data)


async def notify_animal_ready(animal_key: str, chat_id: int) -> None:
    if not centralita_app:
        raise RuntimeError("Centralita no inicializada")

    await centralita_app.bot.send_message(
        chat_id=owner_chat_id(),
        text=(
            f"{ANIMALS[animal_key]['display_name']} ha capturado un chat_id: "
            f"{chat_id}\n"
            f"{ANIMALS[animal_key]['display_name']} ya esta operativo. "
            f"Puedes saludar con /{ANIMALS[animal_key]['central_command']} <mensaje>."
        ),
    )


def append_history(animal_key: str, direction: str, text: str) -> None:
    if not text:
        return

    data = load_data()
    histories = data.setdefault("history", {})
    animal_history = histories.setdefault(animal_key, [])
    animal_history.append(
        {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "direction": direction,
            "text": text,
        }
    )
    histories[animal_key] = animal_history[-MAX_HISTORY_PER_ANIMAL:]
    save_data(data)


def get_history(animal_key: str, limit: int = 10) -> list[dict[str, str]]:
    data = load_data()
    history = data.get("history", {}).get(animal_key, [])
    return history[-limit:]


def format_history_entry(entry: dict[str, str]) -> str:
    direction = entry.get("direction", "")
    speaker = "Tu" if direction == "out" else "Patita"
    text = entry.get("text", "")
    return f"{speaker}: {text}"


def get_schedules() -> list[dict[str, Any]]:
    data = load_data()
    return data.get("schedules", [])


def save_schedules(schedules: list[dict[str, Any]]) -> None:
    data = load_data()
    data["schedules"] = schedules
    save_data(data)


def schedules_paused() -> bool:
    data = load_data()
    return bool(data.get("schedules_paused"))


def set_schedules_paused(paused: bool) -> None:
    data = load_data()
    data["schedules_paused"] = paused
    save_data(data)


def mark_schedule_before_send(schedule_id: str, today: str) -> dict[str, Any] | None:
    schedules = get_schedules()
    for schedule in schedules:
        if schedule["id"] != schedule_id:
            continue

        if schedule.get("kind", "weekly") == "weekly":
            if schedule.get("last_sent_date") == today:
                return None
            schedule["last_sent_date"] = today
        else:
            if schedule.get("sent") or schedule.get("sending"):
                return None
            schedule["sending"] = True

        save_schedules(schedules)
        return schedule
    return None


def mark_schedule_after_send(schedule_id: str, sent: bool) -> None:
    schedules = get_schedules()
    remaining_schedules = []
    changed = False

    for schedule in schedules:
        if schedule["id"] != schedule_id:
            remaining_schedules.append(schedule)
            continue

        changed = True
        if schedule.get("kind", "weekly") == "weekly":
            remaining_schedules.append(schedule)
        elif not sent:
            schedule.pop("sending", None)
            remaining_schedules.append(schedule)

    if changed:
        save_schedules(remaining_schedules)


def parse_schedule_time(value: str) -> tuple[int, int]:
    hour_text, separator, minute_text = value.partition(":")
    if separator != ":":
        raise ValueError("Formato de hora no valido")

    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Hora fuera de rango")
    return hour, minute


def parse_schedule_date(value: str) -> date:
    return datetime.strptime(value, "%d/%m/%Y").date()


def format_schedule(schedule: dict[str, Any]) -> str:
    animal = ANIMALS.get(schedule["animal_key"], {})
    display_name = animal.get("display_name", schedule["animal_key"])
    if schedule["kind"] == "weekly":
        weekday = WEEKDAY_NAMES.get(schedule["weekday"], str(schedule["weekday"]))
        when = f"cada {weekday} a las {schedule['time']}"
    else:
        when = f"el {schedule['date']} a las {schedule['time']}"
    return f"{schedule['id']} - {display_name} - {when} - {schedule['text']}"


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

    animal_commands = "\n".join(
        f"/{animal['central_command']} <mensaje>"
        for animal in ANIMALS.values()
    )
    await update.effective_chat.send_message(
        "Centralita Magica operativa.\n\n"
        "Comandos disponibles:\n"
        f"{animal_commands}\n"
        "/historial <animal> [cantidad]\n"
        "/programar <animal> <dia|DD/MM/AAAA> <HH:MM> <mensaje>\n"
        "/programados\n"
        "/cancelar <id>\n"
        "/pausar_programas\n"
        "/reanudar_programas\n"
        "/status"
    )


async def central_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    lines = ["Estado de la Centralita Magica:"]
    for animal_key, animal in ANIMALS.items():
        if not os.getenv(animal["token_env"]):
            status = f"pendiente de token ({animal['token_env']})"
        else:
            partner_chat_id = get_partner_chat_id(animal_key)
            status = "vinculado" if partner_chat_id else "pendiente de /start"
        lines.append(f"- {animal['display_name']}: {status}")

    await update.effective_chat.send_message("\n".join(lines))


def make_central_animal_handler(animal_key: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await send_as_animal(animal_key, update, context)

    return handler


async def central_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    if not context.args:
        await update.effective_chat.send_message(
            "Uso: /historial <animal> [cantidad]\nEjemplo: /historial castori 10"
        )
        return

    animal_key = context.args[0].lower()
    if animal_key not in ANIMALS:
        await update.effective_chat.send_message(
            "Animal no reconocido. Disponibles: " + ", ".join(sorted(ANIMALS))
        )
        return

    try:
        limit = int(context.args[1]) if len(context.args) > 1 else 10
    except ValueError:
        await update.effective_chat.send_message("La cantidad debe ser un numero.")
        return

    limit = max(1, min(limit, MAX_HISTORY_PER_ANIMAL))
    entries = get_history(animal_key, limit)
    if not entries:
        await update.effective_chat.send_message(
            f"No hay historial guardado para {ANIMALS[animal_key]['display_name']}."
        )
        return

    lines = [
        f"Ultimos {len(entries)} mensajes de {ANIMALS[animal_key]['display_name']}:",
        "",
    ]
    lines.extend(format_history_entry(entry) for entry in entries)
    await update.effective_chat.send_message("\n".join(lines))


async def central_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    if len(context.args) < 4:
        await update.effective_chat.send_message(
            "Uso: /programar <animal> <dia|DD/MM/AAAA> <HH:MM> <mensaje>\n"
            "Ejemplos:\n"
            "/programar mimosuga lunes 09:00 Buena semana, patita.\n"
            "/programar mimosuga 21/03/2026 16:00 Tengo algo que contarte, sol mio."
        )
        return

    animal_key = context.args[0].lower()
    if animal_key not in ANIMALS:
        await update.effective_chat.send_message(
            "Animal no reconocido. Disponibles: " + ", ".join(sorted(ANIMALS))
        )
        return

    try:
        hour, minute = parse_schedule_time(context.args[2])
    except ValueError:
        await update.effective_chat.send_message("Hora no valida. Usa formato HH:MM.")
        return

    text = " ".join(context.args[3:]).strip()
    if not text:
        await update.effective_chat.send_message("El mensaje no puede estar vacio.")
        return

    now = datetime.now(APP_TIMEZONE)
    when_text = context.args[1].lower()
    schedule: dict[str, Any]

    if when_text in WEEKDAYS:
        weekday = WEEKDAYS[when_text]
        last_sent_date = None
        if now.weekday() == weekday and (now.hour, now.minute) >= (hour, minute):
            last_sent_date = now.date().isoformat()

        schedule = {
            "id": uuid.uuid4().hex[:8],
            "kind": "weekly",
            "animal_key": animal_key,
            "weekday": weekday,
            "time": f"{hour:02d}:{minute:02d}",
            "text": text,
            "last_sent_date": last_sent_date,
        }
    else:
        try:
            scheduled_date = parse_schedule_date(context.args[1])
        except ValueError:
            await update.effective_chat.send_message(
                "Fecha o dia no reconocido. Usa lunes, martes... o DD/MM/AAAA."
            )
            return

        scheduled_at = datetime(
            scheduled_date.year,
            scheduled_date.month,
            scheduled_date.day,
            hour,
            minute,
            tzinfo=APP_TIMEZONE,
        )
        if scheduled_at <= now:
            await update.effective_chat.send_message(
                "Esa fecha ya ha pasado. Elige una fecha futura."
            )
            return

        schedule = {
            "id": uuid.uuid4().hex[:8],
            "kind": "once",
            "animal_key": animal_key,
            "date": scheduled_date.isoformat(),
            "time": f"{hour:02d}:{minute:02d}",
            "text": text,
            "sent": False,
        }
    schedules = get_schedules()
    schedules.append(schedule)
    save_schedules(schedules)

    await update.effective_chat.send_message(
        "Programacion creada:\n" + format_schedule(schedule)
    )


async def central_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    schedules = get_schedules()
    if not schedules:
        await update.effective_chat.send_message("No hay mensajes programados.")
        return

    lines = ["Mensajes programados:", ""]
    lines.extend(format_schedule(schedule) for schedule in schedules)
    await update.effective_chat.send_message("\n".join(lines))


async def central_cancel_schedule(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    if not context.args:
        await update.effective_chat.send_message("Uso: /cancelar <id>")
        return

    schedule_id = context.args[0]
    schedules = get_schedules()
    remaining = [schedule for schedule in schedules if schedule["id"] != schedule_id]
    if len(remaining) == len(schedules):
        await update.effective_chat.send_message("No encuentro esa programacion.")
        return

    save_schedules(remaining)
    await update.effective_chat.send_message(f"Programacion {schedule_id} cancelada.")


async def central_pause_schedules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    set_schedules_paused(True)
    await update.effective_chat.send_message("Programaciones pausadas.")


async def central_resume_schedules(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    set_schedules_paused(False)
    await update.effective_chat.send_message("Programaciones reanudadas.")


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

    animal_app = animal_apps.get(animal_key)
    if not animal_app:
        await update.effective_chat.send_message(
            f"{ANIMALS[animal_key]['display_name']} todavia no tiene token configurado "
            f"en {ANIMALS[animal_key]['token_env']}."
        )
        return

    await animal_app.bot.send_chat_action(partner_chat_id, ChatAction.TYPING)
    await animal_app.bot.send_message(chat_id=partner_chat_id, text=text)
    append_history(animal_key, "out", text)
    await update.effective_chat.send_message(
        f"Enviado desde {ANIMALS[animal_key]['display_name']}."
    )


async def send_scheduled_message(schedule: dict[str, Any]) -> bool:
    animal_key = schedule["animal_key"]
    partner_chat_id = get_partner_chat_id(animal_key)
    animal_app = animal_apps.get(animal_key)
    if not partner_chat_id or not animal_app:
        logger.warning(
            "No se puede enviar programacion %s: animal sin chat_id o token",
            schedule["id"],
        )
        return False

    text = schedule["text"]
    await animal_app.bot.send_chat_action(partner_chat_id, ChatAction.TYPING)
    await animal_app.bot.send_message(chat_id=partner_chat_id, text=text)
    append_history(animal_key, "out", text)

    if centralita_app:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                f"Mensaje programado enviado desde "
                f"{ANIMALS[animal_key]['display_name']}:\n{text}"
            ),
        )
    return True


async def scheduler_loop() -> None:
    while True:
        try:
            if schedules_paused():
                await asyncio.sleep(SCHEDULER_POLL_SECONDS)
                continue

            now = datetime.now(APP_TIMEZONE)
            today = now.date().isoformat()
            schedules = get_schedules()

            for schedule in schedules:
                hour, minute = parse_schedule_time(schedule["time"])
                schedule_kind = schedule.get("kind", "weekly")

                if schedule_kind == "weekly":
                    is_due = (
                        now.weekday() == schedule["weekday"]
                        and (now.hour, now.minute) >= (hour, minute)
                        and schedule.get("last_sent_date") != today
                    )
                else:
                    if schedule.get("sent") or schedule.get("sending"):
                        continue
                    scheduled_date = date.fromisoformat(schedule["date"])
                    scheduled_at = datetime(
                        scheduled_date.year,
                        scheduled_date.month,
                        scheduled_date.day,
                        hour,
                        minute,
                        tzinfo=APP_TIMEZONE,
                    )
                    is_due = scheduled_at <= now and not schedule.get("sent")

                if not is_due:
                    continue

                reserved_schedule = mark_schedule_before_send(schedule["id"], today)
                if not reserved_schedule:
                    continue

                sent = await send_scheduled_message(reserved_schedule)
                mark_schedule_after_send(schedule["id"], sent)
        except Exception:
            logger.exception("Error revisando mensajes programados")

        await asyncio.sleep(SCHEDULER_POLL_SECONDS)


async def animal_start(
    animal_key: str,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    if not update.effective_chat:
        return

    chat_id = update.effective_chat.id
    already_started = has_seen_start(animal_key, chat_id) or (
        get_partner_chat_id(animal_key) == chat_id
    )
    set_partner_chat_id(animal_key, chat_id)
    mark_seen_start(animal_key, chat_id)

    if already_started:
        logger.info(
            "%s recibio /start repetido de chat_id %s",
            ANIMALS[animal_key]["display_name"],
            chat_id,
        )
        return

    if not centralita_app:
        raise RuntimeError("Centralita no inicializada")

    await centralita_app.bot.send_message(
        chat_id=owner_chat_id(),
        text=(
            f"{ANIMALS[animal_key]['display_name']} ha capturado un chat_id: "
            f"{chat_id}\n"
            f"{ANIMALS[animal_key]['display_name']} ya esta operativo. "
            f"Puedes saludar con /{ANIMALS[animal_key]['central_command']} <mensaje>."
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
    if not partner_chat_id:
        chat_id = update.effective_chat.id
        set_partner_chat_id(animal_key, chat_id)
        mark_seen_start(animal_key, chat_id)
        await notify_animal_ready(animal_key, chat_id)
        return

    if update.effective_chat.id != partner_chat_id:
        logger.warning(
            "%s recibio mensaje de chat no vinculado: %s",
            ANIMALS[animal_key]["display_name"],
            update.effective_chat.id,
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
        append_history(animal_key, "in", text)
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
    app.add_handler(CommandHandler("historial", central_history))
    app.add_handler(CommandHandler("programar", central_schedule))
    app.add_handler(CommandHandler("programados", central_schedules))
    app.add_handler(CommandHandler("cancelar", central_cancel_schedule))
    app.add_handler(CommandHandler("pausar_programas", central_pause_schedules))
    app.add_handler(CommandHandler("reanudar_programas", central_resume_schedules))
    for animal_key, animal in ANIMALS.items():
        app.add_handler(
            CommandHandler(
                animal["central_command"],
                make_central_animal_handler(animal_key),
            )
        )
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
        token_env = ANIMALS[animal_key]["token_env"]
        if os.getenv(token_env):
            animal_apps[animal_key] = build_animal_app(animal_key)
        else:
            logger.warning(
                "%s no se inicia porque falta %s",
                ANIMALS[animal_key]["display_name"],
                token_env,
            )

    apps = [centralita_app, *animal_apps.values()]
    for app in apps:
        await start_app(app)

    logger.info("Centralita y bots animales en marcha")
    scheduler_task = asyncio.create_task(scheduler_loop())

    try:
        await asyncio.Event().wait()
    finally:
        scheduler_task.cancel()
        for app in reversed(apps):
            await stop_app(app)


if __name__ == "__main__":
    asyncio.run(main())
