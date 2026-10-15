"""Telegram lifecycle and short-lived, private consultation state."""

import asyncio
import logging
import time
from typing import Callable

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from salchicher_service import EMERGENCY_TEXT, UNAVAILABLE_TEXT, generate_care_reply, urgent_signal

logger = logging.getLogger("control-castora.salchicher")
RETENTION_SECONDS = 48 * 60 * 60
MAX_MESSAGES = 24
INTRO = (
    "Soy el Doctor Salchicher, patita: personaje de cuidados y mimos. Puedo hacerte "
    "unas preguntas y proponerte cuidados generales; no soy un medico ni hago diagnosticos.\n\n"
    "Tus mensajes se procesan con IA de OpenAI. La consulta se conserva en el servidor "
    "hasta 48 horas desde tu ultimo mensaje y no pasa a cuentos ni lore. Puedes borrarla "
    "con /olvidar (no borra las copias que queden en Telegram ni los registros del proveedor). "
    "Tu eliges si el Oso, administrador, recibe copia.\n\n"
    "Si es una urgencia, no esperes a este chat: llama al 112."
)


class Salchicher:
    def __init__(self, load: Callable, save: Callable, authorized: Callable, send: Callable,
                 notify: Callable, idle_seconds: int = 90):
        self.load = load
        self.save = save
        self.authorized = authorized
        self.send = send
        self.notify = notify
        self.idle_seconds = max(1, idle_seconds)
        self.tasks: dict[int, asyncio.Task] = {}

    def state(self) -> dict:
        data = self.load()
        return data.get("salchicher", {"enabled": True, "sessions": {}})

    def store(self, state: dict) -> None:
        data = self.load()
        data["salchicher"] = state
        self.save(data)

    def enabled(self) -> bool:
        return bool(self.state().get("enabled", True))

    def session(self, chat_id: int) -> dict | None:
        session = self.state().get("sessions", {}).get(str(chat_id))
        if session and session.get("updated_at", 0) + RETENTION_SECONDS > time.time():
            return session
        return None

    def set_session(self, chat_id: int, session: dict) -> None:
        state = self.state()
        state.setdefault("sessions", {})[str(chat_id)] = session
        self.store(state)

    def forget(self, chat_id: int) -> None:
        task = self.tasks.pop(chat_id, None)
        if task:
            task.cancel()
        state = self.state()
        state.setdefault("sessions", {}).pop(str(chat_id), None)
        self.store(state)

    def set_enabled(self, enabled: bool) -> None:
        state = self.state()
        state["enabled"] = enabled
        if not enabled:
            for task in self.tasks.values():
                task.cancel()
            self.tasks.clear()
            for session in state.get("sessions", {}).values():
                session["pending"] = False
                session["version"] = session.get("version", 0) + 1
        self.store(state)

    def status(self) -> str:
        return (f"Doctor Salchicher: {'encendido' if self.enabled() else 'apagado'}; "
                f"agrupacion {self.idle_seconds}s; "
                f"{sum(not t.done() for t in self.tasks.values())} consultas esperando. "
                "Control: /salchicher_auto on|off")

    def allowed(self, update: Update) -> bool:
        return bool(update.effective_chat and update.effective_chat.type == "private"
                    and update.effective_user
                    and update.effective_user.id in self.authorized()
                    and update.effective_chat.id == update.effective_user.id)

    async def safe_notify(self, text: str) -> None:
        try:
            await self.notify(text)
        except Exception as exc:
            logger.warning("Salchicher admin notification failed: %s", type(exc).__name__)

    async def welcome(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Abrir consulta privada", callback_data="salchicher:private")],
            [InlineKeyboardButton("Abrir y compartir con el Oso", callback_data="salchicher:shared")],
        ])
        await update.effective_chat.send_message(INTRO, reply_markup=keyboard)

    async def consent(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update) or not update.callback_query:
            return
        query = update.callback_query
        if query.data not in {"salchicher:private", "salchicher:shared"}:
            await query.answer("Esta opcion ya no esta disponible.")
            return
        await query.answer()
        chat_id = update.effective_chat.id
        if self.session(chat_id):
            await query.edit_message_reply_markup(reply_markup=None)
            return
        self.set_session(chat_id, {
            "shared": query.data == "salchicher:shared", "history": [], "asked": [],
            "updated_at": time.time(), "version": time.time_ns(), "pending": False,
        })
        await query.edit_message_reply_markup(reply_markup=None)
        await self.send(chat_id, "Consultorio abierto, patita. Cuentame que te pasa y desde cuando.")

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        self.forget(update.effective_chat.id)
        await update.effective_chat.send_message(
            "He borrado la consulta de mi memoria, patita. Las copias en Telegram siguen "
            "en sus chats. Cuando quieras, podemos abrir otra con /consulta."
        )

    async def receive(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update) or not update.message:
            return
        chat_id = update.effective_chat.id
        text = update.message.text or ""
        if text.startswith("/consulta"):
            text = text.partition(" ")[2].strip()
        # This backstop runs before batching, model availability, consent or the on/off switch.
        if urgent_signal(text):
            session = self.session(chat_id)
            self.forget(chat_id)
            await self.send(chat_id, EMERGENCY_TEXT)
            if session and session.get("shared"):
                await self.safe_notify("Doctor Salchicher ha indicado buscar ayuda urgente.\n" + text[:2500])
            return
        if not self.enabled():
            await self.send(chat_id, "El consultorio automatico esta pausado, patita. Si necesitas "
                            "consejo sanitario, contacta con un profesional; no esperes al bot.")
            return
        session = self.session(chat_id)
        if not session:
            await self.welcome(update, context)
            return
        if not text.strip():
            await self.send(chat_id, "Cuentamelo por escrito, patita; aqui no puedo valorar fotos ni audios.")
            return
        if len(text) > 4000:
            await self.send(chat_id, "Cuentame lo principal en un mensaje mas corto, patita.")
            return
        session["history"] = (session["history"] + [{"role": "user", "content": text}])[-MAX_MESSAGES:]
        session["updated_at"] = time.time()
        session["due_at"] = time.time() + self.idle_seconds
        session["version"] += 1
        session["pending"] = True
        self.set_session(chat_id, session)
        self.ensure_worker(chat_id)

    def ensure_worker(self, chat_id: int) -> None:
        if chat_id not in self.tasks or self.tasks[chat_id].done():
            self.tasks[chat_id] = asyncio.create_task(self.worker(chat_id))

    async def worker(self, chat_id: int) -> None:
        try:
            while self.enabled():
                session = self.session(chat_id)
                if not session or not session.get("pending"):
                    return
                remaining = session.get("due_at", 0) - time.time()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    continue
                version = session["version"]
                history = session["history"]
                try:
                    reply, questions = await asyncio.wait_for(
                        generate_care_reply(history, session["asked"]), timeout=70,
                    )
                except Exception as exc:
                    # Do not log health text, model bodies, or provider exception messages.
                    logger.warning("Salchicher generation failed: %s", type(exc).__name__)
                    reply, questions = UNAVAILABLE_TEXT, []
                current = self.session(chat_id)
                if not current or not self.enabled():
                    return
                if current["version"] != version:
                    continue
                # Reserve before sending: a restart/ambiguous timeout must not repeat the message.
                current["pending"] = False
                self.set_session(chat_id, current)
                try:
                    await self.send(chat_id, reply)
                except Exception as exc:
                    logger.warning("Salchicher delivery uncertain: %s", type(exc).__name__)
                    await self.safe_notify("No se pudo confirmar un envio de Salchicher. "
                                           "No se reintentara automaticamente para evitar duplicados.")
                    continue
                latest = self.session(chat_id)
                if latest:
                    latest["history"] = (latest["history"] + [{"role": "assistant", "content": reply}])[-MAX_MESSAGES:]
                    latest["asked"] = list(dict.fromkeys(latest["asked"] + questions))
                    self.set_session(chat_id, latest)
                if current.get("shared"):
                    block = []
                    for entry in reversed(history):
                        if entry["role"] == "assistant":
                            break
                        block.append(entry["content"])
                    await self.safe_notify("Consulta compartida de Doctor Salchicher\n\n"
                                           + "\n".join(reversed(block))[-2500:] + "\n\nRespuesta:\n" + reply)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Salchicher worker failed: %s", type(exc).__name__)
        finally:
            if self.tasks.get(chat_id) is asyncio.current_task():
                self.tasks.pop(chat_id, None)

    def maintenance(self) -> None:
        state = self.state()
        expired = [key for key, session in state.get("sessions", {}).items()
                   if session.get("updated_at", 0) + RETENTION_SECONDS <= time.time()]
        for key in expired:
            self.forget(int(key))
        if self.enabled():
            for key, session in self.state().get("sessions", {}).items():
                if session.get("pending") and int(key) in self.authorized():
                    self.ensure_worker(int(key))

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
