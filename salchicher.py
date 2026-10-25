"""Care episodes shared by Sandra and Miguel, with opt-in retained history."""

import asyncio
import copy
import logging
import time
from typing import Callable
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from salchicher_service import CARE, EMERGENCY_TEXT, UNAVAILABLE_TEXT, generate_care_reply, urgent_signal
from salchicher_copy import retired_automatic_message

logger = logging.getLogger("control-castora.salchicher")
RETENTION_SECONDS = 48 * 60 * 60
INACTIVITY_SECONDS = 30 * 24 * 60 * 60
MAX_MESSAGES = 24
CONSULTATION_GREETING = (
    "¡Adelante, Patita! Te guardé el sillón junto a la ventana. Me pongo las gafitas "
    "y abro mi cuaderno de patos. Cuéntame qué les pasa hoy a esas plumitas "
    "y desde cuándo; iremos pasito a pasito."
)
INTRO = (
    "¡Adelante, Patita! Soy el Doctor Salchicher. Me acomodo las gafitas y abro "
    "el consultorio de cuento: aquí cuidamos picos, alas y plumitas con mucha atención. "
    "Tengo el sillón preparado y el sello de las recetas de mimos sobre la mesa. "
    "Cuando quieras, puedes pasar."
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
        self._expire_consultations()
        session = self.state().get("sessions", {}).get(str(chat_id))
        if session and not session.get("session_id"):
            # Legacy consent is unchanged; this internal identity only fences
            # an old in-flight send from a later session after /olvidar.
            self.set_session(chat_id, session)
        return session

    def set_session(self, chat_id: int, session: dict) -> None:
        state = self.state()
        session.setdefault("session_id", uuid4().hex)
        state.setdefault("sessions", {})[str(chat_id)] = session
        self.store(state)

    def _cancel_worker(self, chat_id: int) -> None:
        task = self.tasks.pop(chat_id, None)
        if task:
            task.cancel()

    def _expire_consultations(self) -> None:
        """Read-time and scheduled expiry; reading an episode is not activity."""
        state = self.state()
        changed = False
        now = time.time()
        for key, session in list(state.get("sessions", {}).items()):
            retained = session.get("consultation_id") and session.get("retained") is True
            ttl = INACTIVITY_SECONDS if retained else RETENTION_SECONDS
            if session.get("updated_at", 0) + ttl > now:
                continue
            self._cancel_worker(int(key))
            if retained:
                record = state.get("consultations", {}).get(key, {}).get(session["consultation_id"])
                if record and record.get("status") == "active":
                    record["status"] = "inactive"
                    record["closed_at"] = session.get("updated_at", 0) + ttl
                    record["closure_reason"] = "inactivity"
            state["sessions"].pop(key, None)
            changed = True
        if changed:
            self.store(state)

    def _require_user(self, chat_id: int) -> None:
        if type(chat_id) is not int or chat_id not in self.authorized():
            raise ValueError("consultation_forbidden")

    @staticmethod
    def _consultation_record(state: dict, chat_id: int, session: dict) -> dict | None:
        if not session.get("consultation_id"):
            return None
        if session.get("retained") is True:
            return state.get("consultations", {}).get(str(chat_id), {}).get(session["consultation_id"])
        return session.get("consultation")

    @staticmethod
    def _public_consultation(record: dict, *, include_messages: bool = True) -> dict:
        fields = ("id", "title", "status", "retained", "created_at", "updated_at",
                  "closed_at", "closure_reason", "care_summary")
        result = {key: copy.deepcopy(record.get(key)) for key in fields}
        if include_messages:
            result["messages"] = [copy.deepcopy(message) for message in record.get("messages", [])
                                  if not retired_automatic_message(message)]
        return result

    def list_consultations(self, chat_id: int) -> list[dict]:
        self._require_user(chat_id)
        self._expire_consultations()
        state = self.state()
        records = list(state.get("consultations", {}).get(str(chat_id), {}).values())
        session = state.get("sessions", {}).get(str(chat_id), {})
        if session.get("consultation_id") and session.get("retained") is not True:
            record = self._consultation_record(state, chat_id, session)
            if record:
                records.append(record)
        return [self._public_consultation(record, include_messages=False)
                for record in sorted(records, key=lambda record: record["created_at"], reverse=True)]

    def get_consultation(self, chat_id: int, consultation_id: str) -> dict | None:
        self._require_user(chat_id)
        self._expire_consultations()
        state = self.state()
        record = state.get("consultations", {}).get(str(chat_id), {}).get(consultation_id)
        if record is None:
            session = state.get("sessions", {}).get(str(chat_id), {})
            if session.get("consultation_id") == consultation_id:
                record = self._consultation_record(state, chat_id, session)
        return self._public_consultation(record) if record else None

    def active_consultation(self, chat_id: int) -> dict | None:
        self._require_user(chat_id)
        session = self.session(chat_id)
        if session and session.get("consultation_id"):
            return self.get_consultation(chat_id, session["consultation_id"])
        return None

    def has_active_consultation(self, chat_id: int) -> bool:
        return self.active_consultation(chat_id) is not None

    def start_consultation(self, chat_id: int, *, retain_history: bool) -> dict:
        """Start only after the caller has collected a separate history choice."""
        self._require_user(chat_id)
        if type(retain_history) is not bool:
            raise ValueError("consultation_consent_required")
        if not self.enabled():
            raise ValueError("consultation_paused")
        self._expire_consultations()
        state = self.state()
        key = str(chat_id)
        existing = state.get("sessions", {}).get(key)
        if existing and existing.get("consultation_id"):
            raise ValueError("consultation_active")
        # A legacy 48-hour session has no archival consent. Starting a new web
        # episode replaces it without importing its history or sharing setting.
        self._cancel_worker(chat_id)
        now = time.time()
        consultation_id = uuid4().hex
        record = {
            "id": consultation_id, "title": "Una visita al doctor de patos", "status": "active",
            "retained": retain_history, "created_at": now, "updated_at": now,
            "closed_at": None, "closure_reason": None, "care_summary": [],
            "messages": [{"role": "assistant", "content": CONSULTATION_GREETING, "created_at": now}],
        }
        session = {
            "consultation_id": consultation_id, "session_id": consultation_id,
            "retained": retain_history, "shared": False,
            "history": [{"role": "assistant", "content": CONSULTATION_GREETING}],
            "asked": [], "updated_at": now, "version": time.time_ns(), "pending": False,
        }
        if retain_history:
            state.setdefault("consultations", {}).setdefault(key, {})[consultation_id] = record
        else:
            session["consultation"] = record
        state.setdefault("sessions", {})[key] = session
        self.store(state)
        return self._public_consultation(record)

    def close_consultation(self, chat_id: int, consultation_id: str) -> dict | None:
        """The person reports feeling better; this is never a medical conclusion."""
        self._require_user(chat_id)
        self._expire_consultations()
        state = self.state()
        key = str(chat_id)
        session = state.get("sessions", {}).get(key, {})
        if session.get("consultation_id") != consultation_id:
            return self.get_consultation(chat_id, consultation_id)
        self._cancel_worker(chat_id)
        record = self._consultation_record(state, chat_id, session)
        if record:
            record["status"] = "recovered"
            record["closed_at"] = time.time()
            record["closure_reason"] = "feeling_better"
        state["sessions"].pop(key, None)
        self.store(state)
        return self._public_consultation(record) if record and session.get("retained") else None

    def delete_consultation(self, chat_id: int, consultation_id: str) -> bool:
        self._require_user(chat_id)
        self._expire_consultations()
        state = self.state()
        key = str(chat_id)
        removed = state.get("consultations", {}).get(key, {}).pop(consultation_id, None) is not None
        session = state.get("sessions", {}).get(key, {})
        if session.get("consultation_id") == consultation_id:
            self._cancel_worker(chat_id)
            state["sessions"].pop(key, None)
            removed = True
        if not state.get("consultations", {}).get(key):
            state.get("consultations", {}).pop(key, None)
        if removed:
            self.store(state)
        return removed

    def _save_message(self, chat_id: int, session: dict, role: str, content: str) -> None:
        state = self.state()
        now = time.time()
        session["history"] = (session["history"] + [{"role": role, "content": content}])[-MAX_MESSAGES:]
        session["updated_at"] = now
        record = self._consultation_record(state, chat_id, session)
        if record:
            record["messages"].append({"role": role, "content": content, "created_at": now})
            record["updated_at"] = now
            if role == "assistant":
                # Only include vetted care sentences actually delivered in this
                # episode. Never infer a diagnosis from the person's messages.
                selected = [text for text in CARE.values() if text in content]
                record["care_summary"] = list(dict.fromkeys(record["care_summary"] + selected))
        state.setdefault("sessions", {})[str(chat_id)] = session
        self.store(state)

    def record_manual_delivery(self, chat_id: int, content: str, consultation_id: str | None) -> None:
        """Keep an actually delivered owner reply in the same active care episode."""
        session = self.session(chat_id)
        if consultation_id and session and session.get("consultation_id") == consultation_id:
            self._save_message(chat_id, session, "assistant", content)

    def forget(self, chat_id: int) -> None:
        self._cancel_worker(chat_id)
        state = self.state()
        state.setdefault("sessions", {}).pop(str(chat_id), None)
        state.get("consultations", {}).pop(str(chat_id), None)
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
        current = self.active_consultation(update.effective_chat.id)
        if current:
            await update.effective_chat.send_message(
                "Tu sillón sigue reservado, Patita. He dejado el cuaderno abierto por "
                "nuestra página y tengo las orejitas atentas. Seguimos por donde íbamos: "
                "¿cómo van hoy esas plumitas?"
            )
            return
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Pasar al sillón", callback_data="salchicher:private")],
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
        await self.send(chat_id, CONSULTATION_GREETING)

    async def reset(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self.allowed(update):
            return
        self.forget(update.effective_chat.id)
        await update.effective_chat.send_message(
            "He dejado en blanco tus páginas de mi cuaderno, Patita. "
            "Cuando quieras, podemos abrir una nueva visita con /consulta."
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
            self._cancel_worker(chat_id)
            if session and session.get("consultation_id"):
                session["pending"] = False
                session["version"] += 1
                self._save_message(chat_id, session, "user", text[:4000])
                self._save_message(chat_id, session, "assistant", EMERGENCY_TEXT)
            state = self.state()
            if session:
                record = self._consultation_record(state, chat_id, session)
                if record:
                    record["status"] = "inactive"
                    record["closed_at"] = time.time()
                    record["closure_reason"] = "urgent_help"
            state.setdefault("sessions", {}).pop(str(chat_id), None)
            self.store(state)
            await self.send(chat_id, EMERGENCY_TEXT)
            if session and session.get("shared"):
                await self.safe_notify("Doctor Salchicher ha indicado buscar ayuda urgente.\n" + text[:2500])
            return
        if not self.enabled():
            await self.send(chat_id, "El sillón del consultorio está descansando un ratito, Patita. "
                            "Te dejo un abrazo de perro con las orejitas por fuera.")
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
        session["due_at"] = time.time() + self.idle_seconds
        session["version"] += 1
        session["pending"] = True
        self._save_message(chat_id, session, "user", text)
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
                consultation_id = session.get("consultation_id")
                session_id = session["session_id"]
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
                if (current.get("consultation_id") != consultation_id
                        or current.get("session_id") != session_id):
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
                if (latest and latest.get("consultation_id") == consultation_id
                        and latest.get("session_id") == session_id):
                    latest["asked"] = list(dict.fromkeys(latest["asked"] + questions))
                    self._save_message(chat_id, latest, "assistant", reply)
                else:
                    # Closing or deleting while transport was pending must not
                    # re-create history or attach a reply to a later episode.
                    return
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
        self._expire_consultations()
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
