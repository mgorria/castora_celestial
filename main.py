import asyncio
import json
import logging
import os
import signal
import socket
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import database
from lore_utils import (
    read_core_lore,
    write_pending_story_markdown,
    write_recent_story_memory_markdown,
)
from story_service import (
    StoryGenerationError,
    generate_court_interrogation,
    generate_court_reply,
    generate_full_story,
    generate_soft_mimosuga_reply,
    generate_story_options,
    openai_available,
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
STARTUP_DELAY_SECONDS = int(os.getenv("STARTUP_DELAY_SECONDS", "8"))
AUTO_REPLY_IDLE_SECONDS = int(os.getenv("AUTO_REPLY_IDLE_SECONDS", "90"))

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
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID") or MI_CHAT_ID
SANDRA_TELEGRAM_ID = os.getenv("SANDRA_TELEGRAM_ID")

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
    },
    "corte": {
        "display_name": "Corte de Pompones y Plumas",
        "token_env": "TOKEN_CORTE",
        "chat_id_env": "CORTE_CHAT_ID",
        "partner_key": "corte_partner_chat_id",
        "central_command": "corte",
    }
}

animal_apps: dict[str, Application] = {}
centralita_app: Application | None = None
lock_socket: socket.socket | None = None
admin_test_story_offers: dict[str, dict[str, Any]] = {}
auto_reply_buffers: dict[str, dict[str, Any]] = {}
auto_reply_tasks: dict[str, asyncio.Task] = {}
court_buffers: dict[str, dict[str, Any]] = {}
court_tasks: dict[str, asyncio.Task] = {}

COURT_DEFENSE_STYLES = {
    "deny": "niega solemnemente los hechos",
    "attenuate": "alega atenuantes de moneria, cansancio o buena intencion",
    "confess": "confiesa parcialmente con arrepentimiento cuqui",
    "sofa": "solicita acuerdo amistoso de sofa y mimos",
}

AUTO_REPLY_DEFAULTS = {
    "mimosuga": {
        "enabled": False,
        "mode": "review",
    }
}


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno {name}")
    return value


def owner_chat_id() -> int:
    if not MI_CHAT_ID:
        raise RuntimeError("Falta la variable de entorno MI_CHAT_ID")
    return int(MI_CHAT_ID)


def admin_chat_id() -> int:
    if not TELEGRAM_ADMIN_ID:
        raise RuntimeError("Falta TELEGRAM_ADMIN_ID o MI_CHAT_ID")
    return int(TELEGRAM_ADMIN_ID)


def is_admin(update: Update) -> bool:
    return bool(update.effective_user and update.effective_user.id == admin_chat_id())


def is_sandra_user(update: Update) -> bool:
    if not update.effective_user:
        return False
    if SANDRA_TELEGRAM_ID:
        return update.effective_user.id == int(SANDRA_TELEGRAM_ID)
    mimosuga_chat_id = get_partner_chat_id("mimosuga")
    if not mimosuga_chat_id:
        return True
    return bool(mimosuga_chat_id and update.effective_chat and update.effective_chat.id == mimosuga_chat_id)


def today_local() -> date:
    return datetime.now(APP_TIMEZONE).date()


def split_telegram_text(text: str, limit: int = 3600) -> list[str]:
    chunks: list[str] = []
    remaining = text.strip()
    while len(remaining) > limit:
        split_at = remaining.rfind("\n\n", 0, limit)
        if split_at == -1:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at == -1:
            split_at = limit
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def ensure_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


async def get_recent_story_memory(narrator: str = "Mimosuga", limit: int = 8) -> list[dict[str, Any]]:
    if not database.db_available():
        return []
    try:
        memories = await database.get_recent_story_memories(narrator, limit)
        write_recent_story_memory_markdown(memories)
        return memories
    except Exception:
        logger.exception("No se pudo cargar memoria reciente de cuentos")
        return []


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


def history_local_datetime(entry: dict[str, str]) -> datetime | None:
    raw_value = entry.get("at")
    if not raw_value:
        return None
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None
    if not parsed.tzinfo:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(APP_TIMEZONE)


def get_mimosuga_day_context() -> dict[str, Any]:
    history = get_history("mimosuga", MAX_HISTORY_PER_ANIMAL)
    today = today_local()
    previous_dates = sorted(
        {
            local_dt.date()
            for entry in history
            if (local_dt := history_local_datetime(entry)) and local_dt.date() < today
        },
        reverse=True,
    )
    previous_date = previous_dates[0] if previous_dates else None

    today_entries: list[dict[str, str]] = []
    previous_entries: list[dict[str, str]] = []
    for entry in history:
        local_dt = history_local_datetime(entry)
        if not local_dt:
            continue
        if local_dt.date() == today:
            today_entries.append(entry)
        elif previous_date and local_dt.date() == previous_date:
            previous_entries.append(entry)

    return {
        "is_first_message_today": not any(
            entry.get("direction") == "in" for entry in today_entries
        ),
        "today_entries": today_entries,
        "previous_day_entries": previous_entries,
        "previous_date": previous_date.isoformat() if previous_date else "",
    }


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


def auto_reply_enabled(animal_key: str) -> bool:
    defaults = AUTO_REPLY_DEFAULTS.get(animal_key, {})
    data = load_data()
    settings = data.get("auto_replies", {}).get(animal_key, {})
    return bool(settings.get("enabled", defaults.get("enabled", False)))


def set_auto_reply_enabled(animal_key: str, enabled: bool) -> None:
    data = load_data()
    auto_replies = data.setdefault("auto_replies", {})
    animal_settings = auto_replies.setdefault(animal_key, {})
    animal_settings["enabled"] = enabled
    save_data(data)


def auto_reply_mode(animal_key: str) -> str:
    defaults = AUTO_REPLY_DEFAULTS.get(animal_key, {})
    data = load_data()
    settings = data.get("auto_replies", {}).get(animal_key, {})
    mode = str(settings.get("mode", defaults.get("mode", "review"))).lower()
    return mode if mode in {"review", "auto"} else "review"


def set_auto_reply_mode(animal_key: str, mode: str) -> None:
    if mode not in {"review", "auto"}:
        raise ValueError("Modo de auto-respuesta no valido")
    data = load_data()
    auto_replies = data.setdefault("auto_replies", {})
    animal_settings = auto_replies.setdefault(animal_key, {})
    animal_settings["mode"] = mode
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


def next_schedule_time(schedule: dict[str, Any], now: datetime) -> datetime | None:
    try:
        hour, minute = parse_schedule_time(schedule["time"])
    except (KeyError, ValueError):
        return None

    if schedule.get("kind", "weekly") == "weekly":
        weekday = int(schedule["weekday"])
        days_ahead = (weekday - now.weekday()) % 7
        candidate = datetime(
            now.year,
            now.month,
            now.day,
            hour,
            minute,
            tzinfo=APP_TIMEZONE,
        ) + timedelta(days=days_ahead)
        if candidate <= now:
            candidate += timedelta(days=7)
        return candidate

    if schedule.get("sent") or schedule.get("sending"):
        return None
    try:
        scheduled_date = date.fromisoformat(schedule["date"])
    except (KeyError, ValueError):
        return None
    return datetime(
        scheduled_date.year,
        scheduled_date.month,
        scheduled_date.day,
        hour,
        minute,
        tzinfo=APP_TIMEZONE,
    )


def format_short_schedule(schedule: dict[str, Any], when: datetime) -> str:
    display_name = ANIMALS.get(schedule.get("animal_key"), {}).get(
        "display_name",
        str(schedule.get("animal_key", "animal")),
    )
    text = str(schedule.get("text", ""))
    if len(text) > 70:
        text = text[:67] + "..."
    return f"{when.strftime('%d/%m %H:%M')} - {display_name}: {text}"


def court_defense_keyboard(case_id: int, accused: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Niego los hechos", callback_data=f"courtdef:{case_id}:{accused}:deny"),
                InlineKeyboardButton("Atenuantes", callback_data=f"courtdef:{case_id}:{accused}:attenuate"),
            ],
            [
                InlineKeyboardButton("Confieso un poco", callback_data=f"courtdef:{case_id}:{accused}:confess"),
                InlineKeyboardButton("Acuerdo de sofa", callback_data=f"courtdef:{case_id}:{accused}:sofa"),
            ],
        ]
    )


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
        "/admin_ultimos\n"
        "/admin_ver ID\n"
        "/admin_aprobar ID\n"
        "/admin_descartar ID\n"
        "/admin_canon ID\n"
        "/admin_lore\n"
        "/admin_memoria_cuentos\n"
        "/admin_cuento_prueba [mimosuga]\n"
        "/acusar <hechos>\n"
        "/alegar <texto>\n"
        "/caso_estado\n"
        "/mimosuga_auto <on|off|status>\n"
        "/status"
    )


async def central_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    now = datetime.now(APP_TIMEZONE)
    lines = [
        "Estado general de Control Castori",
        f"Hora local: {now.strftime('%d/%m/%Y %H:%M')}",
        "",
        "Bots:",
    ]
    for animal_key, animal in ANIMALS.items():
        if not os.getenv(animal["token_env"]):
            status = f"pendiente de token ({animal['token_env']})"
        else:
            partner_chat_id = get_partner_chat_id(animal_key)
            status = "vinculado" if partner_chat_id else "pendiente de /start"
        lines.append(f"- {animal['display_name']}: {status}")

    lines.append("")
    lines.append("Sistema:")
    lines.append(f"- Railway/worker: activo si estas recibiendo este mensaje")
    lines.append(f"- Base de datos: {'conectada' if database.db_available() else 'no disponible'}")
    lines.append(f"- OpenAI: {'configurado' if openai_available() else 'no configurado'}")
    lines.append(f"- Archivo de estado: {DATA_FILE}")

    schedules = get_schedules()
    active_schedules = [
        schedule for schedule in schedules
        if schedule.get("kind", "weekly") == "weekly" or not schedule.get("sent")
    ]
    upcoming = []
    for schedule in active_schedules:
        when = next_schedule_time(schedule, now)
        if when:
            upcoming.append((when, schedule))
    upcoming.sort(key=lambda item: item[0])
    lines.append("")
    lines.append("Programaciones:")
    lines.append(f"- Estado: {'pausadas' if schedules_paused() else 'activas'}")
    lines.append(f"- Activas: {len(active_schedules)}")
    if upcoming:
        lines.append("- Proximas:")
        for when, schedule in upcoming[:3]:
            lines.append(f"  {format_short_schedule(schedule, when)}")
    else:
        lines.append("- Proximas: ninguna")

    auto_status = "encendida" if auto_reply_enabled("mimosuga") else "apagada"
    pending_batches = sum(
        1 for key, task in auto_reply_tasks.items()
        if key.startswith("mimosuga:") and not task.done()
    )
    lines.append("")
    lines.append("Mimosuga automatica:")
    lines.append(f"- Respuestas suaves: {auto_status}")
    mode_text = "envio automatico" if auto_reply_mode("mimosuga") == "auto" else "revision previa"
    lines.append(f"- Modo: {mode_text}")
    lines.append(f"- Espera para agrupar mensajes: {AUTO_REPLY_IDLE_SECONDS} segundos")
    lines.append(f"- Lotes esperando: {pending_batches}")

    lines.append("")
    lines.append("Cuentos y lore:")
    if database.db_available():
        try:
            counts = await database.get_system_status_counts()
            lines.append(f"- Historias totales: {counts.get('stories_total', 0)}")
            lines.append(f"- Historias pendientes: {counts.get('stories_pending', 0)}")
            lines.append(f"- Historias canon: {counts.get('stories_canon', 0)}")
            lines.append(f"- Opciones de cuento activas: {counts.get('active_story_offers', 0)}")
            lines.append(f"- Respuestas suaves pendientes de revisar: {counts.get('auto_reply_pending', 0)}")
            lines.append(f"- Causas activas en la Corte: {counts.get('court_cases_active', 0)}")
        except Exception:
            logger.exception("No se pudieron cargar contadores de estado")
            lines.append("- Contadores de base de datos: error al consultar")
    else:
        lines.append("- Base de datos no disponible; cuentos desactivados")

    lines.append(f"- Cuento diario: se renueva a las 00:00 ({APP_TIMEZONE.key})")
    lines.append("")
    lines.append("Comandos utiles:")
    lines.append("- /programados, /historial mimosuga 10, /admin_ultimos, /acusar, /caso_estado")

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


async def central_mimosuga_auto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return

    if not context.args:
        status = "encendidas" if auto_reply_enabled("mimosuga") else "apagadas"
        mode_text = "auto" if auto_reply_mode("mimosuga") == "auto" else "revision"
        await update.effective_chat.send_message(
            f"Respuestas suaves de Mimosuga: {status}.\n"
            f"Modo: {mode_text}.\n"
            "Uso: /mimosuga_auto on, /mimosuga_auto auto, /mimosuga_auto revision, "
            "/mimosuga_auto off o /mimosuga_auto status"
        )
        return

    action = context.args[0].lower()
    if action in {"on", "activar", "encender"}:
        set_auto_reply_enabled("mimosuga", True)
        set_auto_reply_mode("mimosuga", "review")
        await update.effective_chat.send_message(
            "Respuestas suaves de Mimosuga encendidas en modo revision previa. "
            "Patita no recibira nada sin que tu pulses Enviar."
        )
        return

    if action in {"auto", "automatico", "automatica"}:
        set_auto_reply_enabled("mimosuga", True)
        set_auto_reply_mode("mimosuga", "auto")
        await update.effective_chat.send_message(
            "Respuestas suaves de Mimosuga encendidas en modo automatico. "
            "Si la IA considera que el mensaje es trivial, Mimosuga respondera sola; "
            "si lo ve delicado o importante, te avisara sin enviar nada."
        )
        return

    if action in {"revision", "revisar", "manual"}:
        set_auto_reply_enabled("mimosuga", True)
        set_auto_reply_mode("mimosuga", "review")
        await update.effective_chat.send_message(
            "Respuestas suaves de Mimosuga en modo revision previa. "
            "Recibiras propuesta con botones antes de enviar."
        )
        return

    if action in {"off", "desactivar", "apagar"}:
        set_auto_reply_enabled("mimosuga", False)
        await update.effective_chat.send_message("Respuestas suaves de Mimosuga apagadas.")
        return

    if action in {"status", "estado"}:
        status = "encendidas" if auto_reply_enabled("mimosuga") else "apagadas"
        mode_text = "envio automatico" if auto_reply_mode("mimosuga") == "auto" else "revision previa"
        pending_batches = sum(
            1 for key, task in auto_reply_tasks.items()
            if key.startswith("mimosuga:") and not task.done()
        )
        await update.effective_chat.send_message(
            f"Respuestas suaves de Mimosuga: {status}.\n"
            f"Modo actual: {mode_text}.\n"
            f"Espera para agrupar mensajes: {AUTO_REPLY_IDLE_SECONDS} segundos.\n"
            f"Lotes de mensajes esperando: {pending_batches}."
        )
        return

    await update.effective_chat.send_message(
        "Uso: /mimosuga_auto on, /mimosuga_auto auto, /mimosuga_auto revision, "
        "/mimosuga_auto off o /mimosuga_auto status"
    )


async def central_accuse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return
    if not database.db_available() or not openai_available():
        await update.effective_chat.send_message("La Corte necesita base de datos y OpenAI configurados.")
        return

    accusation = " ".join(context.args).strip()
    if not accusation:
        await update.effective_chat.send_message(
            "Uso: /acusar <hechos>\n"
            "Ejemplo: /acusar Patita cruzo el pasillo sin entregar beso reglamentario."
        )
        return

    partner_chat_id = get_partner_chat_id("corte")
    court_app = animal_apps.get("corte")
    if not partner_chat_id or not court_app:
        await update.effective_chat.send_message(
            "La Corte todavia no esta vinculada. Patita debe abrir el bot de la Corte y enviar /start una vez."
        )
        return

    try:
        case_id = await database.create_court_case(
            chat_id=partner_chat_id,
            accusation=accusation,
            accuser="admin",
        )
    except Exception as exc:
        await update.effective_chat.send_message(str(exc))
        return

    text = (
        "NOTIFICACION FORMAL DE LA CORTE DE POMPONES Y PLUMAS\n\n"
        f"Causa #{case_id}\n\n"
        "Se hace saber a Patita que ha sido abierta causa por los siguientes hechos:\n\n"
        f"{accusation}\n\n"
        "La compareciente dispone de este canal para presentar alegaciones, excusas, "
        "pucheros, atenuantes de moneria o pruebas de inocencia.\n\n"
        "Antes de declarar, seleccione estrategia de defensa para que la Sala formule "
        "interrogatorio."
    )
    await court_app.bot.send_message(
        chat_id=partner_chat_id,
        text=text,
        reply_markup=court_defense_keyboard(case_id, "patita"),
    )
    append_history("corte", "out", text)
    await update.effective_chat.send_message(f"Causa #{case_id} enviada a la Corte.")


async def central_court_plead(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return
    if not database.db_available() or not openai_available():
        await update.effective_chat.send_message("La Corte necesita base de datos y OpenAI configurados.")
        return

    text = " ".join(context.args).strip()
    if not text:
        await update.effective_chat.send_message(
            "Uso: /alegar <texto>\n"
            "Ejemplo: /alegar Niego los hechos y solicito atenuante por estar haciendo cafe."
        )
        return

    partner_chat_id = get_partner_chat_id("corte")
    if not partner_chat_id:
        await update.effective_chat.send_message("La Corte no esta vinculada.")
        return

    case = await database.get_active_court_case(partner_chat_id)
    if not case:
        await update.effective_chat.send_message("No hay proceso abierto en la Corte.")
        return

    await queue_court_submission(
        chat_id=partner_chat_id,
        sender="admin",
        incoming_text=text,
    )
    await update.effective_chat.send_message(
        "Alegacion presentada ante la Corte. "
        f"La Sala esperara {AUTO_REPLY_IDLE_SECONDS} segundos antes de dictar sentencia."
    )


async def central_court_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_owner(update):
        return
    if not database.db_available():
        await update.effective_chat.send_message("Base de datos no disponible.")
        return
    partner_chat_id = get_partner_chat_id("corte")
    if not partner_chat_id:
        await update.effective_chat.send_message("La Corte no esta vinculada.")
        return
    case = await database.get_latest_court_case(partner_chat_id)
    if not case:
        await update.effective_chat.send_message("No hay causas registradas en la Corte.")
        return
    lines = [
        f"Ultima causa de la Corte #{case['id']}",
        f"Estado: {case['status']}",
        f"Acusacion: {case['accusation']}",
    ]
    if case.get("verdict"):
        lines.append(f"Veredicto: {case['verdict']}")
    if case.get("sentence_text"):
        lines.append(f"Sentencia: {case['sentence_text']}")
    await update.effective_chat.send_message("\n".join(lines))


async def court_user_accuse(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat:
        return
    partner_chat_id = get_partner_chat_id("corte")
    if partner_chat_id and update.effective_chat.id != partner_chat_id:
        return
    if not database.db_available() or not openai_available():
        await update.effective_chat.send_message(
            "La Corte no encuentra ahora mismo sus sellos oficiales. Intente presentar denuncia mas tarde."
        )
        return

    accusation = " ".join(context.args).strip()
    if not accusation:
        await update.effective_chat.send_message(
            "Para presentar denuncia formal, use:\n/acusar hechos del caso"
        )
        return

    try:
        case_id = await database.create_court_case(
            chat_id=update.effective_chat.id,
            accusation=accusation,
            accuser="patita",
        )
    except Exception:
        await update.effective_chat.send_message(
            "La Corte informa que ya consta un proceso abierto. "
            "No se admiten dos expedientes encima de la misma mesa con pompones."
        )
        return

    text = (
        "DENUNCIA ADMITIDA A TRAMITE\n\n"
        f"Causa #{case_id}\n\n"
        "La Corte de Pompones y Plumas admite la denuncia presentada por Patita "
        "y concede a Miguel turno de alegaciones.\n\n"
        "La Sala queda con las plumas levantadas y el sello preparado."
    )
    await update.effective_chat.send_message(text)
    append_history("corte", "in", f"[Denuncia de Patita] {accusation}")
    append_history("corte", "out", text)

    if centralita_app:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                f"Patita ha abierto causa #{case_id} en la Corte.\n"
                f"Acusacion: {accusation}\n\n"
                "Puedes escoger estrategia de defensa con los botones o presentar alegaciones con:\n"
                "/alegar <texto>"
            ),
            reply_markup=court_defense_keyboard(case_id, "admin"),
        )


async def court_defense_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return

    parts = (query.data or "").split(":")
    if len(parts) != 4:
        await query.answer()
        return
    _, case_id_text, accused, style_key = parts
    if accused == "admin" and query.from_user.id != owner_chat_id():
        await query.answer("Solo Miguel puede escoger esta defensa.", show_alert=True)
        return
    if accused == "patita":
        partner_chat_id = get_partner_chat_id("corte")
        if partner_chat_id and query.message.chat_id != partner_chat_id:
            await query.answer("Esta defensa pertenece a otra causa.", show_alert=True)
            return

    try:
        case_id = int(case_id_text)
    except ValueError:
        await query.answer("Causa no valida.", show_alert=True)
        return
    style = COURT_DEFENSE_STYLES.get(style_key)
    if not style:
        await query.answer("Estrategia no valida.", show_alert=True)
        return
    if not database.db_available() or not openai_available():
        await query.answer("La Corte no tiene sellos disponibles.", show_alert=True)
        return

    case = await database.get_active_court_case(query.message.chat_id if accused == "patita" else get_partner_chat_id("corte") or 0)
    if not case or case["id"] != case_id:
        await query.answer("La causa ya no esta activa.", show_alert=True)
        return

    await query.answer("Estrategia incorporada al acta.")
    await database.add_court_message(case_id, accused, f"[Estrategia de defensa] {style}")
    try:
        precedents = await database.get_recent_court_precedents(3)
        interrogation = await generate_court_interrogation(
            accusation=case["accusation"],
            accused=accused,
            defense_style=style,
            precedents=precedents,
        )
        question = interrogation["question"]
    except Exception as exc:
        logger.exception("No se pudo generar interrogatorio de la Corte")
        question = (
            "La Corte solicita a la parte compareciente que exponga, con la mayor "
            "solemnidad blandita posible, sus alegaciones antes de sentencia."
        )

    await database.add_court_message(case_id, "court", question)
    await query.message.reply_text(question)
    if accused == "admin":
        await query.message.reply_text("Responde con /alegar <texto> para presentar defensa.")
    else:
        await query.message.reply_text("Puede contestar con sus alegaciones en uno o varios mensajes.")


async def story_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_user:
        return

    if not is_sandra_user(update):
        await update.effective_chat.send_message(
            "Ay, patita, este cuaderno todavia no esta preparado para este caminito."
        )
        return

    if not database.db_available() or not openai_available():
        await update.effective_chat.send_message(
            "Ay, mi patita, Mimosuga no encuentra ahora mismo su cuaderno de cuentos. "
            "Vuelve un poquito mas tarde, que lo dejare sobre la mesa."
        )
        return

    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    await database.upsert_user(user_id, user_name, "sandra")
    requested_topic = " ".join(context.args).strip() if context.args else ""
    if len(requested_topic) > 180:
        requested_topic = requested_topic[:180].rstrip()

    if await database.daily_story_consumed(user_id, today_local()):
        await update.effective_chat.send_message(
            "Ay, mi patita, hoy ya te he contado una historia. Guardare otra "
            "dobladita bajo mi mantita para manana, que las historias tambien "
            "necesitan dormir un poco."
        )
        return

    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    try:
        recent = await get_recent_story_memory("Mimosuga")
        options = await generate_story_options(
            narrator="Mimosuga",
            recent_summaries=recent,
            requested_topic=requested_topic or None,
        )
        offer_id = await database.create_story_offer(user_id, "Mimosuga", options)
    except Exception:
        logger.exception("No se pudieron generar opciones de cuento")
        await update.effective_chat.send_message(
            "Ay, sol mio, se me han desordenado las paginas del cuaderno. "
            "Dame un ratito y lo intento otra vez."
        )
        return

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    options[0]["title"],
                    callback_data=f"cuento:{offer_id}:0",
                )
            ],
            [
                InlineKeyboardButton(
                    options[1]["title"],
                    callback_data=f"cuento:{offer_id}:1",
                )
            ],
        ]
    )
    topic_line = f"Sobre: {requested_topic}\n\n" if requested_topic else ""
    message = (
        "Ven, patita, que Mimosuga tiene dos cuentos preparados. "
        "Elige el que te llame mas suave:\n\n"
        f"{topic_line}"
        f"1. {options[0]['title']}\n{options[0]['teaser']}\n\n"
        f"2. {options[1]['title']}\n{options[1]['teaser']}"
    )
    await update.effective_chat.send_message(message, reply_markup=keyboard)


async def story_option_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return

    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    _, offer_id, option_index_text = parts
    try:
        option_index = int(option_index_text)
    except ValueError:
        await query.message.reply_text("Ay, patita, ese boton se ha quedado torcido.")
        return

    if not database.db_available() or not openai_available():
        await query.message.reply_text(
            "Ay, mi patita, ahora mismo no puedo abrir el cuaderno de cuentos."
        )
        return

    offer = await database.get_story_offer(offer_id)
    if not offer or offer.get("consumed_at") or offer.get("expires_at") <= datetime.now(timezone.utc):
        await query.message.reply_text(
            "Ay, ese cuento se ha quedado antiguo en la repisa. Pideme /cuento y te saco dos nuevos."
        )
        return

    if offer["telegram_user_id"] != query.from_user.id:
        await query.message.reply_text("Ay, este cuento estaba guardado para otra patita.")
        return

    if await database.daily_story_consumed(query.from_user.id, today_local()):
        await query.message.reply_text(
            "Ay, mi patita, hoy ya recibiste tu cuento. Manana tendre otro guardadito."
        )
        return

    options = ensure_json_list(offer["options"])
    if option_index < 0 or option_index >= len(options):
        await query.message.reply_text("Ay, ese boton ya no apunta a ningun cuento.")
        return

    if not await database.reserve_story_offer(offer_id):
        await query.message.reply_text(
            "Ay, ese boton ya esta siendo atendido. Mimosuga va despacito, pero va."
        )
        return

    selected_option = options[option_index]
    await query.message.reply_text(
        "Mimosuga se acomoda el chal y abre el cuaderno. Dame un momentito, patita."
    )

    try:
        recent = await get_recent_story_memory("Mimosuga")
        story = await generate_full_story(
            narrator="Mimosuga",
            selected_option=selected_option,
            offered_options=options,
            recent_summaries=recent,
        )
        story_id = await database.create_story(
            title=story["title"],
            full_text=story["full_text"],
            summary=story["summary"],
            narrator="Mimosuga",
            selected_option=selected_option.get("title", ""),
            offered_options=options,
            characters_used=story.get("characters_used"),
            locations_used=story.get("locations_used"),
            new_lore_proposals=story.get("new_lore_proposals"),
            delivered_to_user_id=query.from_user.id,
        )
        story_record = {
            **story,
            "id": story_id,
            "status": "pending",
            "narrator": "Mimosuga",
            "created_at": datetime.now(timezone.utc),
            "new_lore_proposals": story.get("new_lore_proposals") or [],
        }
        write_pending_story_markdown(story_record)

        for chunk in split_telegram_text(story["full_text"]):
            await context.bot.send_chat_action(query.message.chat_id, ChatAction.TYPING)
            await query.message.reply_text(chunk)

        await database.mark_story_delivered(story_id)
        append_history(
            "mimosuga",
            "out",
            f"[Cuento entregado #{story_id}] {story['title']}: {story['summary']}",
        )
        consumed = await database.consume_daily_story(query.from_user.id, today_local(), story_id)
        await get_recent_story_memory("Mimosuga")
        if not consumed:
            logger.warning("Cuento %s entregado pero limite diario ya existia", story_id)
        await notify_admin_story(story_id, story, options, selected_option)
    except Exception:
        logger.exception("No se pudo generar o enviar el cuento")
        await database.release_story_offer(offer_id)
        await query.message.reply_text(
            "Ay, mi patita, el cuento se me ha quedado a medias entre las paginas. "
            "No cuenta como cuento de hoy; lo intentamos otra vez cuando quieras."
        )


async def notify_admin_story(
    story_id: int,
    story: dict[str, Any],
    options: list[dict[str, Any]],
    selected_option: dict[str, Any],
) -> None:
    if not centralita_app:
        return

    summary = (
        f"Cuento generado #{story_id}\n"
        f"Titulo: {story['title']}\n"
        "Estado: pending\n"
        f"Opcion elegida: {selected_option.get('title', '')}\n"
        f"Tipo: {story.get('story_type', selected_option.get('story_type', ''))}\n"
        f"Forma: {story.get('narrative_shape', selected_option.get('narrative_shape', ''))}\n"
        f"Pulso: {story.get('emotional_tone', selected_option.get('emotional_tone', ''))}\n\n"
        "Opciones ofrecidas:\n"
        f"- {options[0].get('title', '')} ({options[0].get('story_type', '')}, {options[0].get('narrative_shape', '')}, {options[0].get('emotional_tone', '')}): {options[0].get('teaser', '')}\n"
        f"- {options[1].get('title', '')} ({options[1].get('story_type', '')}, {options[1].get('narrative_shape', '')}, {options[1].get('emotional_tone', '')}): {options[1].get('teaser', '')}\n\n"
        f"Resumen: {story['summary']}"
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Aprobar", callback_data=f"adminstory:{story_id}:approved"),
                InlineKeyboardButton("Descartar", callback_data=f"adminstory:{story_id}:rejected"),
                InlineKeyboardButton("Canon", callback_data=f"adminstory:{story_id}:canon"),
            ]
        ]
    )
    await centralita_app.bot.send_message(
        chat_id=admin_chat_id(),
        text=summary,
        reply_markup=keyboard,
    )
    for chunk in split_telegram_text(story["full_text"]):
        await centralita_app.bot.send_message(chat_id=admin_chat_id(), text=chunk)


async def admin_test_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_admin(update):
        return

    if not openai_available():
        await update.effective_chat.send_message("OPENAI_API_KEY no esta configurada.")
        return

    narrator = context.args[0].lower() if context.args else "mimosuga"
    if narrator != "mimosuga":
        await update.effective_chat.send_message("De momento solo existe prueba para mimosuga.")
        return

    await update.effective_chat.send_message(
        "Generando opciones de prueba de Mimosuga. No se guardara ni consumira limites."
    )

    try:
        recent = await get_recent_story_memory("Mimosuga")
        options = await generate_story_options(narrator="Mimosuga", recent_summaries=recent)
    except Exception as exc:
        logger.exception("No se pudieron generar opciones de prueba")
        detail = str(exc)
        if len(detail) > 1200:
            detail = detail[:1200] + "..."
        await update.effective_chat.send_message(
            "No se pudieron generar opciones de prueba.\n\n"
            f"Detalle tecnico para admin:\n{type(exc).__name__}: {detail}"
        )
        return

    offer_id = uuid.uuid4().hex[:8]
    admin_test_story_offers[offer_id] = {
        "options": options,
        "recent": recent,
        "created_at": datetime.now(timezone.utc),
    }
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    options[0].get("title", "Opcion 1"),
                    callback_data=f"adminteststory:{offer_id}:0",
                )
            ],
            [
                InlineKeyboardButton(
                    options[1].get("title", "Opcion 2"),
                    callback_data=f"adminteststory:{offer_id}:1",
                )
            ],
        ]
    )
    await update.effective_chat.send_message(
        "Elige una opcion de prueba. Solo se generara para ti.\n\n"
        f"1. {options[0].get('title', '')}\n{options[0].get('teaser', '')}\n\n"
        f"2. {options[1].get('title', '')}\n{options[1].get('teaser', '')}",
        reply_markup=keyboard,
    )


async def admin_test_story_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return
    if query.from_user.id != admin_chat_id():
        await query.answer("Solo el administrador puede generar pruebas.", show_alert=True)
        return

    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    _, offer_id, option_index_text = parts
    offer = admin_test_story_offers.pop(offer_id, None)
    if not offer:
        await query.message.reply_text(
            "Esta prueba ya no esta disponible. Pide otra con /admin_cuento_prueba mimosuga."
        )
        return

    try:
        option_index = int(option_index_text)
        options = offer["options"]
        selected_option = options[option_index]
    except (ValueError, IndexError):
        await query.message.reply_text("Esa opcion de prueba no es valida.")
        return

    await query.message.reply_text(
        "Generando cuento de prueba con la opcion elegida. No se guardara ni consumira limites."
    )

    try:
        recent = await get_recent_story_memory("Mimosuga")
        story = await generate_full_story(
            narrator="Mimosuga",
            selected_option=selected_option,
            offered_options=options,
            recent_summaries=recent or offer["recent"],
        )
    except Exception as exc:
        logger.exception("No se pudo generar cuento de prueba elegido")
        detail = str(exc)
        if len(detail) > 1200:
            detail = detail[:1200] + "..."
        await query.message.reply_text(
            "No se pudo generar el cuento de prueba.\n\n"
            f"Detalle tecnico para admin:\n{type(exc).__name__}: {detail}"
        )
        return

    meta = (
        "Cuento de prueba generado. No guardado, no canon, no entregado a Patita.\n\n"
        f"Opcion usada: {selected_option.get('title', '')}\n"
        f"Tipo: {story.get('story_type', selected_option.get('story_type', ''))}\n"
        f"Forma: {story.get('narrative_shape', selected_option.get('narrative_shape', ''))}\n"
        f"Pulso: {story.get('emotional_tone', selected_option.get('emotional_tone', ''))}\n"
        f"Titulo: {story['title']}\n"
        f"Resumen: {story['summary']}"
    )
    await query.message.reply_text(meta)
    for chunk in split_telegram_text(story["full_text"]):
        await query.message.reply_text(chunk)


async def admin_latest_stories(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_admin(update):
        return
    if not database.db_available():
        await update.effective_chat.send_message("Base de datos no disponible.")
        return

    stories = await database.get_latest_stories(10)
    if not stories:
        await update.effective_chat.send_message("No hay historias generadas.")
        return

    lines = ["Ultimas historias:", ""]
    for story in stories:
        created_at = story["created_at"].astimezone(APP_TIMEZONE).strftime("%d/%m/%Y %H:%M")
        lines.append(
            f"{story['id']} - {story['title']} - {created_at} - {story['status']}"
        )
    await update.effective_chat.send_message("\n".join(lines))


async def admin_view_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_admin(update):
        return
    if not context.args:
        await update.effective_chat.send_message("Uso: /admin_ver ID")
        return
    story = await get_admin_story_from_args(update, context)
    if not story:
        return

    meta = (
        f"#{story['id']} - {story['title']}\n"
        f"Estado: {story['status']}\n"
        f"Narrador: {story['narrator']}\n"
        f"Resumen: {story['summary']}\n"
        f"Opcion elegida: {story.get('selected_option') or ''}"
    )
    await update.effective_chat.send_message(meta)
    for chunk in split_telegram_text(story["full_text"]):
        await update.effective_chat.send_message(chunk)


async def get_admin_story_from_args(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> dict[str, Any] | None:
    if not database.db_available():
        await update.effective_chat.send_message("Base de datos no disponible.")
        return None
    try:
        story_id = int(context.args[0])
    except (ValueError, IndexError):
        await update.effective_chat.send_message("ID no valido.")
        return None
    story = await database.get_story(story_id)
    if not story:
        await update.effective_chat.send_message("No encuentro esa historia.")
        return None
    return story


async def admin_update_story_status(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    status: str,
) -> None:
    if not update.effective_chat or not is_admin(update):
        return
    story = await get_admin_story_from_args(update, context)
    if not story:
        return
    await database.update_story_status(story["id"], status)
    await update.effective_chat.send_message(f"Historia {story['id']} marcada como {status}.")


async def admin_approve_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_update_story_status(update, context, "approved")


async def admin_reject_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_update_story_status(update, context, "rejected")


async def admin_canon_story(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_update_story_status(update, context, "canon")


async def admin_lore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_admin(update):
        return
    lore = read_core_lore()
    for chunk in split_telegram_text(lore, limit=3500):
        await update.effective_chat.send_message(chunk)


async def admin_story_memory(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not is_admin(update):
        return
    memories = await get_recent_story_memory("Mimosuga")
    if not memories:
        await update.effective_chat.send_message("No hay memoria reciente de cuentos.")
        return
    lines = ["Memoria reciente de cuentos:", ""]
    for story in memories:
        characters = story.get("characters_used") or []
        if not isinstance(characters, list):
            characters = []
        lines.extend(
            [
                f"#{story.get('id')} - {story.get('title')}",
                f"Personajes: {', '.join(map(str, characters)) or 'No registrados'}",
                f"Resumen: {story.get('summary', '')}",
                "",
            ]
        )
    for chunk in split_telegram_text("\n".join(lines), limit=3500):
        await update.effective_chat.send_message(chunk)


async def admin_story_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return
    if query.from_user.id != admin_chat_id():
        await query.answer("Solo el administrador puede revisar cuentos.", show_alert=True)
        return
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer()
        return
    _, story_id_text, status = parts
    if status not in {"approved", "rejected", "canon"}:
        await query.answer()
        return
    try:
        story_id = int(story_id_text)
    except ValueError:
        await query.answer("ID no valido.", show_alert=True)
        return
    if not database.db_available():
        await query.answer("Base de datos no disponible.", show_alert=True)
        return
    updated = await database.update_story_status(story_id, status)
    if updated:
        await query.answer(f"Historia marcada como {status}.")
        if query.message:
            await query.message.reply_text(f"Historia {story_id} marcada como {status}.")
    else:
        await query.answer("No encuentro esa historia.", show_alert=True)


async def auto_reply_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return
    if query.from_user.id != owner_chat_id():
        await query.answer("Solo Miguel puede revisar respuestas.", show_alert=True)
        return

    await query.answer()
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    _, draft_id_text, action = parts
    try:
        draft_id = int(draft_id_text)
    except ValueError:
        await query.message.reply_text("Borrador no valido.")
        return

    if not database.db_available():
        await query.message.reply_text("Base de datos no disponible.")
        return

    if action == "reject":
        rejected = await database.reject_auto_reply_draft(draft_id, query.from_user.id)
        if rejected:
            await query.message.reply_text(f"Respuesta suave #{draft_id} descartada.")
        else:
            draft = await database.get_auto_reply_draft(draft_id)
            status = draft.get("status") if draft else "no encontrada"
            await query.message.reply_text(
                f"No se pudo descartar la respuesta #{draft_id}. Estado actual: {status}."
            )
        return

    if action != "send":
        return

    sent, message = await send_auto_reply_draft(draft_id, query.from_user.id)
    await query.message.reply_text(message)


async def send_auto_reply_draft(draft_id: int, admin_user_id: int) -> tuple[bool, str]:
    draft = await database.reserve_auto_reply_draft(draft_id, admin_user_id)
    if not draft:
        current = await database.get_auto_reply_draft(draft_id)
        status = current.get("status") if current else "no encontrada"
        return False, f"Esa respuesta ya no esta pendiente. Estado actual: {status}."

    animal_key = draft["animal_key"]
    animal_app = animal_apps.get(animal_key)
    partner_chat_id = get_partner_chat_id(animal_key)
    if not animal_app or not partner_chat_id:
        await database.release_auto_reply_draft(draft_id)
        return (
            False,
            f"No puedo enviar la respuesta #{draft_id}: "
            f"{ANIMALS[animal_key]['display_name']} no esta vinculado.",
        )

    try:
        await animal_app.bot.send_chat_action(partner_chat_id, ChatAction.TYPING)
        await animal_app.bot.send_message(
            chat_id=partner_chat_id,
            text=draft["proposed_text"],
        )
        append_history(animal_key, "out", draft["proposed_text"])
        await database.mark_auto_reply_draft_sent(draft_id)
        return True, f"Respuesta suave #{draft_id} enviada por Mimosuga."
    except Exception:
        logger.exception("No se pudo enviar respuesta automatica aprobada")
        await database.release_auto_reply_draft(draft_id)
        return (
            False,
            f"No se pudo enviar la respuesta #{draft_id}. Revisa logs antes de intentarlo de nuevo.",
        )


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
        if animal_key == "corte":
            append_history(animal_key, "in", text)
            await centralita_app.bot.send_message(chat_id=owner_chat_id(), text=text)
            await queue_court_allegation(update, context, text)
            return

        day_context = get_mimosuga_day_context() if animal_key == "mimosuga" else None
        append_history(animal_key, "in", text)
        await centralita_app.bot.send_message(chat_id=owner_chat_id(), text=text)
        await queue_auto_reply_draft(animal_key, update, text, day_context)
    else:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "Ha llegado un mensaje no textual. "
                "Para revisarlo, abre temporalmente el bot del animal correspondiente."
            ),
        )


async def queue_court_allegation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    incoming_text: str,
) -> None:
    if not update.effective_chat or not centralita_app:
        return
    if not database.db_available() or not openai_available():
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text="La Corte ha recibido alegaciones, pero falta base de datos u OpenAI.",
        )
        return

    case = await database.get_active_court_case(update.effective_chat.id)
    if not case:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=(
                "La Corte informa, con sello provisional, que no consta ningun proceso "
                "abierto en este momento. Para presentar denuncia formal use /acusar."
            ),
        )
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text="La Corte recibio un mensaje, pero no hay causa activa.",
        )
        return

    await queue_court_submission(
        chat_id=update.effective_chat.id,
        sender="patita",
        incoming_text=incoming_text,
    )


async def queue_court_submission(
    *,
    chat_id: int,
    sender: str,
    incoming_text: str,
) -> None:
    if not centralita_app:
        return
    case = await database.get_active_court_case(chat_id)
    if not case:
        return

    await database.add_court_message(case["id"], sender, incoming_text)
    buffer_key = f"corte:{chat_id}"
    was_new_buffer = buffer_key not in court_buffers
    if was_new_buffer:
        court_buffers[buffer_key] = {
            "case_id": case["id"],
            "chat_id": chat_id,
            "sender": sender,
            "messages": [],
        }
    buffer = court_buffers[buffer_key]
    buffer["case_id"] = case["id"]
    buffer["sender"] = sender
    buffer["messages"].append(incoming_text)

    existing_task = court_tasks.get(buffer_key)
    if existing_task and not existing_task.done():
        existing_task.cancel()
    court_tasks[buffer_key] = asyncio.create_task(process_court_buffer_after_idle(buffer_key))

    if was_new_buffer:
        subject = "Patita amplia declaracion" if sender == "patita" else "Miguel amplia defensa"
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "La Corte toma nota de la alegacion y esperara "
                f"{AUTO_REPLY_IDLE_SECONDS} segundos por si {subject}."
            ),
        )


async def process_court_buffer_after_idle(buffer_key: str) -> None:
    try:
        await asyncio.sleep(AUTO_REPLY_IDLE_SECONDS)
        await process_court_buffer(buffer_key)
    except asyncio.CancelledError:
        return


async def process_court_buffer(buffer_key: str) -> None:
    buffer = court_buffers.pop(buffer_key, None)
    court_tasks.pop(buffer_key, None)
    if not buffer or not centralita_app:
        return

    chat_id = int(buffer["chat_id"])
    court_app = animal_apps.get("corte")
    if not court_app:
        return
    case = await database.get_active_court_case(chat_id)
    if not case or case["id"] != buffer["case_id"]:
        return

    new_messages = [str(message).strip() for message in buffer.get("messages", []) if str(message).strip()]
    allegation_sender = str(buffer.get("sender", "patita"))
    messages = await database.get_court_messages(case["id"])
    try:
        precedents = await database.get_recent_court_precedents(5)
        decision = await generate_court_reply(
            accusation=case["accusation"],
            messages=messages,
            new_allegations=new_messages,
            new_allegations_sender=allegation_sender,
            precedents=precedents,
        )
    except Exception as exc:
        logger.exception("No se pudo generar respuesta de la Corte")
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=f"La Corte no pudo deliberar: {type(exc).__name__}: {exc}",
        )
        return

    reply = decision["reply"]
    await court_app.bot.send_chat_action(chat_id, ChatAction.TYPING)
    await court_app.bot.send_message(chat_id=chat_id, text=reply)
    append_history("corte", "out", reply)
    await database.add_court_message(case["id"], "court", reply)
    allegations_text = "\n".join(f"- {message}" for message in new_messages) or "- Sin alegaciones registradas"
    allegations_label = "Alegaciones de Miguel" if allegation_sender == "admin" else "Alegaciones de Patita"

    if decision["status"] == "sentence":
        verdict = decision.get("verdict") or "culpabilidad con atenuantes de moneria"
        sentence_text = decision.get("sentence") or reply
        await database.sentence_court_case(
            case_id=case["id"],
            verdict=verdict,
            sentence_text=sentence_text,
        )
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                f"La Corte ha dictado sentencia en la causa #{case['id']}.\n"
                f"Acusacion: {case['accusation']}\n\n"
                f"{allegations_label}:\n"
                f"{allegations_text}\n\n"
                f"Veredicto: {verdict}\n"
                f"Condena: {sentence_text}\n\n"
                "Mensaje enviado por la Corte a Patita:\n"
                f"{reply}"
            ),
        )
    else:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                f"La Corte ha pausado la causa #{case['id']} por prudencia.\n"
                f"Acusacion: {case['accusation']}\n\n"
                f"{allegations_label}:\n"
                f"{allegations_text}\n\n"
                "Mensaje enviado por la Corte a Patita:\n"
                f"{reply}"
            ),
        )


async def queue_auto_reply_draft(
    animal_key: str,
    update: Update,
    incoming_text: str,
    day_context: dict[str, Any] | None,
) -> None:
    if animal_key != "mimosuga" or not auto_reply_enabled("mimosuga"):
        return
    if not update.effective_chat or not centralita_app:
        return
    if not database.db_available():
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text="Auto Mimosuga esta encendido, pero la base de datos no esta disponible.",
        )
        return
    if not openai_available():
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text="Auto Mimosuga esta encendido, pero OPENAI_API_KEY no esta configurada.",
        )
        return

    buffer_key = f"{animal_key}:{update.effective_chat.id}"
    was_new_buffer = buffer_key not in auto_reply_buffers
    if was_new_buffer:
        auto_reply_buffers[buffer_key] = {
            "animal_key": animal_key,
            "chat_id": update.effective_chat.id,
            "messages": [],
            "first_message_today": bool(day_context and day_context.get("is_first_message_today")),
            "started_at": datetime.now(timezone.utc),
        }
    buffer = auto_reply_buffers[buffer_key]
    buffer["messages"].append(incoming_text)
    if day_context and day_context.get("is_first_message_today"):
        buffer["first_message_today"] = True

    existing_task = auto_reply_tasks.get(buffer_key)
    if existing_task and not existing_task.done():
        existing_task.cancel()
    auto_reply_tasks[buffer_key] = asyncio.create_task(process_auto_reply_buffer_after_idle(buffer_key))

    if was_new_buffer:
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "Auto Mimosuga abre un lote y esperara "
                f"{AUTO_REPLY_IDLE_SECONDS} segundos antes de proponer una sola respuesta."
            ),
        )


async def process_auto_reply_buffer_after_idle(buffer_key: str) -> None:
    try:
        await asyncio.sleep(AUTO_REPLY_IDLE_SECONDS)
        await process_auto_reply_buffer(buffer_key)
    except asyncio.CancelledError:
        return


async def process_auto_reply_buffer(buffer_key: str) -> None:
    buffer = auto_reply_buffers.pop(buffer_key, None)
    auto_reply_tasks.pop(buffer_key, None)
    if not buffer or not centralita_app:
        return
    if not auto_reply_enabled("mimosuga"):
        return
    if not database.db_available() or not openai_available():
        return

    messages = [str(message).strip() for message in buffer.get("messages", []) if str(message).strip()]
    if not messages:
        return

    try:
        day_context = get_mimosuga_day_context()
        recent_history = get_history("mimosuga", 20)
        latest_story = await database.get_latest_delivered_story(
            narrator="Mimosuga",
            telegram_user_id=int(buffer["chat_id"]),
        )
        draft = await generate_soft_mimosuga_reply(
            incoming_messages=messages,
            recent_history=recent_history,
            today_history=day_context["today_entries"],
            previous_day_history=day_context["previous_day_entries"],
            previous_date=day_context["previous_date"],
            is_first_message_today=bool(buffer.get("first_message_today")),
            latest_story=latest_story,
        )
    except Exception as exc:
        logger.exception("No se pudo generar borrador automatico de Mimosuga")
        detail = str(exc)
        if len(detail) > 600:
            detail = detail[:600] + "..."
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "No se pudo preparar respuesta suave de Mimosuga.\n\n"
                f"{type(exc).__name__}: {detail}"
            ),
        )
        return

    if not draft.get("should_reply"):
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                "Auto Mimosuga recomienda no responder sola a este mensaje.\n"
                f"Motivo: {draft.get('reason') or 'mensaje no trivial'}"
            ),
        )
        return

    proposed_text = str(draft.get("reply", "")).strip()
    if not proposed_text:
        return

    incoming_text = "\n".join(f"- {message}" for message in messages)
    draft_id = await database.create_auto_reply_draft(
        animal_key="mimosuga",
        incoming_chat_id=int(buffer["chat_id"]),
        incoming_text=incoming_text,
        proposed_text=proposed_text,
        reason=str(draft.get("reason") or ""),
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Enviar", callback_data=f"autoreply:{draft_id}:send"),
                InlineKeyboardButton("Descartar", callback_data=f"autoreply:{draft_id}:reject"),
            ]
        ]
    )
    admin_message = (
        f"Respuesta suave propuesta por Mimosuga #{draft_id}\n"
        f"Motivo: {draft.get('reason') or 'charla ligera'}\n\n"
        f"Modo: {draft.get('reply_style') or 'no indicado'}\n\n"
        "Mensajes agrupados de Patita:\n"
        f"{incoming_text}\n\n"
        "Propuesta:\n"
        f"{proposed_text}"
    )

    if auto_reply_mode("mimosuga") == "auto":
        sent, result_message = await send_auto_reply_draft(draft_id, owner_chat_id())
        await centralita_app.bot.send_message(
            chat_id=owner_chat_id(),
            text=(
                f"Auto Mimosuga #{draft_id}: {result_message}\n\n"
                f"Motivo: {draft.get('reason') or 'charla ligera'}\n"
                f"Modo: {draft.get('reply_style') or 'no indicado'}\n\n"
                "Mensajes agrupados de Patita:\n"
                f"{incoming_text}\n\n"
                "Respuesta enviada:\n"
                f"{proposed_text}"
                if sent
                else admin_message + f"\n\nResultado: {result_message}"
            ),
        )
        return

    await centralita_app.bot.send_message(
        chat_id=owner_chat_id(),
        text=admin_message,
        reply_markup=keyboard,
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
    app.add_handler(CommandHandler("mimosuga_auto", central_mimosuga_auto))
    app.add_handler(CommandHandler("acusar", central_accuse))
    app.add_handler(CommandHandler("alegar", central_court_plead))
    app.add_handler(CommandHandler("caso_estado", central_court_status))
    app.add_handler(CommandHandler("admin_ultimos", admin_latest_stories))
    app.add_handler(CommandHandler("admin_ver", admin_view_story))
    app.add_handler(CommandHandler("admin_aprobar", admin_approve_story))
    app.add_handler(CommandHandler("admin_descartar", admin_reject_story))
    app.add_handler(CommandHandler("admin_canon", admin_canon_story))
    app.add_handler(CommandHandler("admin_lore", admin_lore))
    app.add_handler(CommandHandler("admin_memoria_cuentos", admin_story_memory))
    app.add_handler(CommandHandler("admin_cuento_prueba", admin_test_story))
    app.add_handler(CallbackQueryHandler(admin_test_story_callback, pattern=r"^adminteststory:"))
    app.add_handler(CallbackQueryHandler(admin_story_status_callback, pattern=r"^adminstory:"))
    app.add_handler(CallbackQueryHandler(auto_reply_callback, pattern=r"^autoreply:"))
    app.add_handler(CallbackQueryHandler(court_defense_callback, pattern=r"^courtdef:"))
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
    if animal_key == "mimosuga":
        app.add_handler(CommandHandler("cuento", story_request))
        app.add_handler(CallbackQueryHandler(story_option_callback, pattern=r"^cuento:"))
    if animal_key == "corte":
        app.add_handler(CommandHandler("acusar", court_user_accuse))
        app.add_handler(CallbackQueryHandler(court_defense_callback, pattern=r"^courtdef:"))
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

    if STARTUP_DELAY_SECONDS > 0:
        logger.info("Esperando %s segundos antes de iniciar polling", STARTUP_DELAY_SECONDS)
        await asyncio.sleep(STARTUP_DELAY_SECONDS)

    await database.init_db()

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
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        await stop_event.wait()
    finally:
        scheduler_task.cancel()
        for app in reversed(apps):
            await stop_app(app)
        await database.close_db()


if __name__ == "__main__":
    asyncio.run(main())
