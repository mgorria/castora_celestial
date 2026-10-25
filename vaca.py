"""Private Telegram conversations and durable wish lists for the Vaca Mágica."""

import asyncio
import copy
import logging
import re
import time
from typing import Callable

from vaca_service import cow_voice, generate_vaca_reply, validate_generated_wish_text
from vaca_campaigns import public_chat_anticipation

logger = logging.getLogger("control-castora.vaca")
MAX_MESSAGES = 24
MAX_WISHES = 60
MAX_PENDING_MESSAGES = 12
MAX_PENDING_CHARS = 16000
UNAVAILABLE_TEXT = (
    "Patita, se me ha enredado el lápiz entre las pezuñas. No he cambiado tu lista. "
    "Puedes seguir apuntando deseos con /pedir regalo y consultarlos con /lista."
)
WELCOME = (
    "¡Patita! 🐄✨\n\n"
    "¡Me hace mucha ilusión tenerte por aquí! Soy tu Vaca Mágica, la Mugidora, "
    "y tengo un cuaderno de ilusiones con tu nombre.\n\n"
    "Cuéntame qué regalos te harían sonreír y los iremos apuntando juntas. También "
    "puede escapárseme alguna pista… pero mis visitas son un secreto de pezuña.\n\n"
    "Ponte cómoda, patita: aquí hay mucho cariño y un rinconcito de magia para ti."
)
WELCOME_BACK = (
    "¡Patita, qué alegría verte otra vez! 🐄✨ Tu cuaderno de ilusiones sigue aquí, "
    "entre mis pezuñas. Cuéntame, que tengo muchas ganas de leerte."
)
HELP = (
    "Soy tu Vaca Mágica, patita. 🐄✨ Puedes contarme tus ilusiones y te ayudaré a "
    "guardarlas en nuestro cuaderno. ¡Me hace mucha ilusión leerte!\n\n"
    "/lista — ver tus deseos\n"
    "/pedir regalo — apuntar un deseo directamente (puedes añadir un enlace)\n"
    "/quitar w1 — quitar un deseo por su identificador\n"
    "/favorito w1 — poner o quitar la estrella de favorito\n"
    "/olvidar — borrar nuestra conversación, conservando la lista\n\n"
    "También puedes pedirme cambios hablando con naturalidad. El Oso puede ver tu "
    "lista para ayudarme con las sorpresas. Apuntar un deseo no promete que vaya a "
    "llegar: mis visitas siguen siendo un secreto de pezuña."
)


class Vaca:
    def __init__(self, load: Callable, save: Callable, authorized: Callable,
                 send: Callable, notify: Callable, idle_seconds: int = 20):
        self.load = load
        self.save = save
        self.authorized = authorized
        self.send = send
        self.notify = notify
        self.idle_seconds = max(1, idle_seconds)
        self.tasks: dict[int, asyncio.Task] = {}
        self.failed_versions: dict[int, int] = {}

    def state(self) -> dict:
        # Detached snapshots prevent a failed save from mutating an in-memory store.
        return copy.deepcopy(self.load().get("vaca", {"enabled": True, "sessions": {}}))

    def store(self, state: dict) -> None:
        data = copy.deepcopy(self.load())
        data["vaca"] = state
        self.save(data)

    def enabled(self) -> bool:
        return bool(self.state().get("enabled", True))

    def session(self, chat_id: int) -> dict | None:
        return self.state().get("sessions", {}).get(str(chat_id))

    def new_session(self) -> dict:
        return {"history": [], "wishes": [], "next_wish_id": 1,
                "version": 0, "pending": False, "pending_texts": [],
                "updated_at": time.time()}

    def set_session(self, chat_id: int, session: dict) -> None:
        state = self.state()
        state.setdefault("sessions", {})[str(chat_id)] = session
        self.store(state)

    def allowed(self, update) -> bool:
        return bool(update.effective_chat and update.effective_chat.type == "private"
                    and update.effective_user
                    and update.effective_user.id in self.authorized()
                    and update.effective_chat.id == update.effective_user.id)

    def _invalidate(self, session: dict) -> None:
        session["version"] = session.get("version", 0) + 1
        session["pending"] = False
        session["pending_texts"] = []
        session["updated_at"] = time.time()

    def set_enabled(self, enabled: bool) -> None:
        state = self.state()
        state["enabled"] = bool(enabled)
        if not enabled:
            for session in state.get("sessions", {}).values():
                self._invalidate(session)
        self.store(state)
        if not enabled:
            for task in self.tasks.values():
                task.cancel()
            self.tasks.clear()

    def status(self) -> str:
        state = self.state()
        wishes = sum(len(s.get("wishes", [])) for s in state.get("sessions", {}).values())
        return (f"Vaca Mágica: {'encendida' if state.get('enabled', True) else 'pausada'}; "
                f"agrupación {self.idle_seconds}s; {wishes} deseos; "
                f"{sum(not task.done() for task in self.tasks.values())} conversaciones pendientes. "
                "Control: /vaca_auto on|off")

    async def safe_notify(self, text: str) -> None:
        try:
            await self.notify(text)
        except Exception as exc:
            logger.warning("Vaca owner notification failed: %s", type(exc).__name__)

    async def _deliver(self, chat_id: int, text: str) -> bool:
        try:
            await self.send(chat_id, text)
            return True
        except Exception as exc:
            logger.warning("Vaca delivery uncertain: %s", type(exc).__name__)
            await self.safe_notify("No se pudo confirmar un envío de la Vaca Mágica. "
                                   "No se reintentará automáticamente para evitar duplicados.")
            return False

    def remember_outgoing(self, chat_id: int, text: str) -> None:
        """Record only public text that has already been sent, never gift plans."""
        if chat_id not in self.authorized():
            return
        session = self.session(chat_id) or self.new_session()
        session["version"] = session.get("version", 0) + 1
        session["updated_at"] = time.time()
        self._append_assistant(session, text)
        self.set_session(chat_id, session)
        if session.get("pending") and self.enabled():
            self.ensure_worker(chat_id)

    def _append_assistant(self, session: dict, text: str) -> None:
        # Keep the active user block last even when a public clue arrives while
        # the model is working. Evidence remains scoped to these pending messages.
        pending = session.get("pending_texts", []) if session.get("pending") else []
        history = session.get("history", [])
        if pending:
            history = history[:-len(pending)]
        session["history"] = (history + [{"role": "assistant", "content": text[:4000]}]
                              + [{"role": "user", "content": text} for text in pending])[-MAX_MESSAGES:]

    async def welcome(self, update, context) -> None:
        if self.allowed(update):
            await self._welcome_chat(update.effective_chat.id)

    async def _welcome_chat(self, chat_id: int) -> None:
        session = self.session(chat_id) or self.new_session()
        greeting = cow_voice(WELCOME_BACK if session.get("welcomed") else WELCOME)
        if not await self._deliver(chat_id, greeting):
            return
        # Read again after the send so another message cannot lose its wishes or
        # pending request while the welcome is in flight.
        session = self.session(chat_id) or self.new_session()
        session["welcomed"] = True
        session["version"] = session.get("version", 0) + 1
        session["updated_at"] = time.time()
        self._append_assistant(session, greeting)
        try:
            self.set_session(chat_id, session)
        except Exception as exc:
            logger.warning("Vaca welcome save failed: %s", type(exc).__name__)
            return
        if session.get("pending") and self.enabled():
            self.ensure_worker(chat_id)

    def format_wishlist(self, chat_id: int) -> str:
        wishes = (self.session(chat_id) or {}).get("wishes", [])
        heading = "📒 Cuaderno de ilusiones de Patita"
        if not wishes:
            return heading + "\n\nTodavía no hay deseos apuntados. Cuéntame qué te hace ilusión, patita."
        lines = [heading, ""]
        for wish in wishes:
            lines.append(f"{wish['id']}. {'⭐ ' if wish.get('favorite') else ''}{wish['name']}")
            if wish.get("details"):
                lines.append(wish["details"])
            if wish.get("url"):
                lines.append(wish["url"])
            lines.append("")
        lines.append("Puedes usar /quitar w1 o /favorito w1 con el identificador de cada deseo.")
        return "\n".join(lines)

    def _new_wish(self, session: dict, name: str, details: str = "", url: str = "",
                  favorite: bool = False) -> dict:
        if len(session.get("wishes", [])) >= MAX_WISHES:
            raise ValueError("wishlist full")
        next_id = max(1, int(session.get("next_wish_id", 1)))
        used = {wish["id"] for wish in session.get("wishes", [])}
        while f"w{next_id}" in used:
            next_id += 1
        session["next_wish_id"] = next_id + 1
        wish = {"id": f"w{next_id}", "name": name, "details": details,
                "url": url, "favorite": favorite, "created_at": time.time()}
        session.setdefault("wishes", []).append(wish)
        return wish

    async def _command(self, chat_id: int, command: str, argument: str) -> None:
        if command == "/start":
            await self._welcome_chat(chat_id)
            return
        if command in {"/ayuda", "/help"}:
            await self._deliver(chat_id, cow_voice(HELP))
            return
        if command == "/lista":
            await self._deliver(chat_id, self.format_wishlist(chat_id))
            return
        session = self.session(chat_id) or self.new_session()
        changed = False
        if command == "/olvidar":
            self._invalidate(session)
            session["history"] = []
            reply = "He borrado nuestra conversación de mi memoria, patita. Tu lista sigue guardada."
        elif command == "/pedir":
            if not argument:
                await self._deliver(chat_id, "Dime el deseo después de /pedir, patita. Por ejemplo: /pedir zapatillas rosas talla 38")
                return
            urls = re.findall(r"https?://\S+", argument)
            url = urls[0] if len(urls) == 1 else ""
            name = argument.replace(url, "", 1).strip() if url else argument
            name = name or "Regalo del enlace"
            if len(name) > 240 or len(url) > 1200:
                await self._deliver(chat_id, "Pon un nombre de hasta 240 caracteres y un enlace de hasta 1200, patita. Podemos añadir detalles después.")
                return
            duplicate = next((w for w in session["wishes"]
                              if w["name"].casefold() == name.casefold() and w.get("url", "") == url), None)
            if duplicate:
                await self._deliver(chat_id, f"Ese deseo ya está en tu cuaderno, patita: {duplicate['id']}. {duplicate['name']}")
                return
            if len(session["wishes"]) >= MAX_WISHES:
                await self._deliver(chat_id, "El cuaderno tiene sus 60 deseos ocupados, patita. Quita alguno con /quitar para dejar sitio.")
                return
            wish = self._new_wish(session, name=name, url=url)
            self._invalidate(session)
            reply = f"Apuntado en tu cuaderno, patita: {wish['id']}. {wish['name']}"
            changed = True
        elif command in {"/quitar", "/favorito"}:
            wish = next((w for w in session["wishes"] if w["id"] == argument.lower()), None)
            if not wish:
                await self._deliver(chat_id, "No encuentro ese identificador, patita. Consulta /lista y usa, por ejemplo, " + command + " w1.")
                return
            if command == "/quitar":
                session["wishes"].remove(wish)
                reply = f"Quitado de tu cuaderno: {wish['id']}. {wish['name']}"
            else:
                wish["favorite"] = not wish.get("favorite", False)
                reply = f"{'⭐ Marcado como favorito' if wish['favorite'] else 'Estrella de favorito retirada'}: {wish['id']}. {wish['name']}"
            self._invalidate(session)
            changed = True
        else:
            await self._deliver(chat_id, "No conozco ese comando, patita. Usa /ayuda para ver lo que podemos hacer.")
            return
        if command != "/olvidar":
            session["history"] = (session.get("history", []) + [
                {"role": "user", "content": f"{command} {argument}".strip()},
                {"role": "assistant", "content": reply},
            ])[-MAX_MESSAGES:]
        try:
            self.set_session(chat_id, session)
        except Exception as exc:
            logger.warning("Vaca command save failed: %s", type(exc).__name__)
            await self._deliver(chat_id, "No he podido guardar el cambio, patita. Prueba otra vez dentro de un poquito.")
            return
        await self._deliver(chat_id, reply)
        if changed:
            await self.safe_notify(f"Vaca Mágica — lista actualizada (chat {chat_id})\n{reply}")

    async def receive(self, update, context) -> None:
        if not self.allowed(update) or not update.message:
            return
        chat_id = update.effective_chat.id
        text = (update.message.text or "").strip()
        if not text:
            await self._deliver(chat_id, "Cuéntamelo por escrito, patita. Puedes pegar enlaces; todavía no leo fotos ni audios.")
            return
        if len(text) > 4000:
            await self._deliver(chat_id, "Escríbemelo en mensajes de hasta 4000 caracteres, patita.")
            return
        if text.startswith("/"):
            command, _, argument = text.partition(" ")
            await self._command(chat_id, command.split("@", 1)[0].lower(), argument.strip())
            return
        if not self.enabled():
            await self._deliver(chat_id, "Estoy descansando un poquito, patita. Tu cuaderno sigue abierto con /lista, /pedir, /quitar y /favorito.")
            return
        session = self.session(chat_id) or self.new_session()
        pending_texts = session.get("pending_texts", [])
        if len(pending_texts) >= MAX_PENDING_MESSAGES or sum(map(len, pending_texts)) + len(text) > MAX_PENDING_CHARS:
            await self._deliver(chat_id, "Déjame terminar de leer lo anterior, patita; tengo las pezuñas llenas de notas.")
            return
        session["history"] = (session.get("history", []) + [{"role": "user", "content": text}])[-MAX_MESSAGES:]
        session["pending_texts"] = pending_texts + [text]
        session["updated_at"] = time.time()
        session["due_at"] = time.time() + self.idle_seconds
        session["version"] = session.get("version", 0) + 1
        session["pending"] = True
        try:
            self.set_session(chat_id, session)
        except Exception as exc:
            logger.warning("Vaca incoming save failed: %s", type(exc).__name__)
            await self._deliver(chat_id, "No he podido guardar tu mensaje, patita. Prueba otra vez dentro de un poquito.")
            return
        self.ensure_worker(chat_id)

    def ensure_worker(self, chat_id: int) -> None:
        if self.failed_versions.get(chat_id) == (self.session(chat_id) or {}).get("version"):
            return
        if chat_id not in self.tasks or self.tasks[chat_id].done():
            self.tasks[chat_id] = asyncio.create_task(self.worker(chat_id))

    def _apply_operations(self, session: dict, operations, evidence_block: str) -> list[str]:
        """Validate a complete batch on a detached session before any persistence."""
        if not isinstance(operations, list) or len(operations) > 8:
            raise ValueError("invalid operations")
        confirmations = []
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError("invalid operation")
            action = operation.get("action")
            identity = operation.get("id")
            evidence = operation.get("evidence")
            if (action not in {"add", "update", "remove"} or not isinstance(identity, str)
                    or len(identity) > 40 or not isinstance(evidence, str) or not evidence
                    or len(evidence) > 4000 or evidence not in evidence_block):
                raise ValueError("invalid operation evidence")
            for key, limit in (("name", 240), ("details", 1000), ("url", 1200)):
                if not isinstance(operation.get(key), str) or len(operation[key]) > limit:
                    raise ValueError("invalid wish field")
            favorite = operation.get("favorite")
            if favorite is not None and not isinstance(favorite, bool):
                raise ValueError("invalid favorite")
            if operation["url"] and not re.match(r"^https?://[^\s]+$", operation["url"]):
                raise ValueError("invalid URL")
            if action != "remove" and not operation["name"].strip():
                raise ValueError("empty wish name")
            wishes = session.setdefault("wishes", [])
            if action == "add":
                if identity:
                    raise ValueError("new wish id must be empty")
                validate_generated_wish_text(operation)
                wish = self._new_wish(session, operation["name"], operation["details"],
                                      operation["url"], bool(favorite))
                confirmations.append(f"Apuntado: {wish['id']}. {wish['name']}")
                continue
            wish = next((item for item in wishes if item["id"] == identity), None)
            if not wish:
                raise ValueError("unknown wish id")
            validate_generated_wish_text(operation, wish)
            if action == "remove":
                wishes.remove(wish)
                confirmations.append(f"Quitado: {wish['id']}. {wish['name']}")
            else:
                for key in ("name", "details", "url"):
                    wish[key] = operation[key]
                if favorite is not None:
                    wish["favorite"] = favorite
                confirmations.append(f"Actualizado: {wish['id']}. {wish['name']}")
        return confirmations

    async def worker(self, chat_id: int) -> None:
        try:
            while self.enabled() and chat_id in self.authorized():
                session = self.session(chat_id)
                if not session or not session.get("pending"):
                    return
                remaining = session.get("due_at", 0) - time.time()
                if remaining > 0:
                    await asyncio.sleep(remaining)
                    continue
                version = session["version"]
                pending_texts = session.get("pending_texts", [])
                evidence = "\n".join(pending_texts)
                anticipation = public_chat_anticipation(self.load(), chat_id)
                try:
                    result = await asyncio.wait_for(generate_vaca_reply(
                        copy.deepcopy(session.get("history", [])),
                        copy.deepcopy(session.get("wishes", [])),
                        anticipation,
                    ), timeout=70)
                    if (not isinstance(result, dict) or not isinstance(result.get("reply"), str)
                            or not result["reply"].strip() or len(result["reply"]) > 1800
                            or not isinstance(result.get("show_list"), bool)):
                        raise ValueError("invalid model response")
                    candidate = copy.deepcopy(session)
                    confirmations = self._apply_operations(candidate, result.get("operations"), evidence)
                    reply = cow_voice(result["reply"])
                    if confirmations:
                        reply += "\n\n" + "\n".join(confirmations)
                    failed = False
                except Exception as exc:
                    logger.warning("Vaca generation failed: %s", type(exc).__name__)
                    candidate = copy.deepcopy(session)
                    confirmations = []
                    result = {"show_list": False}
                    reply = UNAVAILABLE_TEXT
                    failed = True
                current = self.session(chat_id)
                if not current or not self.enabled() or chat_id not in self.authorized():
                    return
                if current.get("version") != version:
                    continue
                # A paused/cancelled/revised visit must not leave an in-flight
                # response building anticipation from an obsolete permission.
                if public_chat_anticipation(self.load(), chat_id) != anticipation:
                    continue
                # Commit list changes and consume the batch BEFORE delivery. In particular,
                # an ambiguous Telegram timeout must never add wishes or send a reply twice.
                candidate["pending"] = False
                candidate["pending_texts"] = []
                candidate["version"] = version + 1
                candidate["updated_at"] = time.time()
                try:
                    self.set_session(chat_id, candidate)
                except Exception as exc:
                    logger.error("Vaca result save failed: %s", type(exc).__name__)
                    # Do not retry a generation on every maintenance tick while storage is down.
                    self.failed_versions[chat_id] = version
                    await self._deliver(chat_id, "No he podido guardar el cambio, patita. Tu lista no se ha confirmado; prueba /lista cuando vuelva el cuaderno.")
                    return
                if result["show_list"]:
                    reply += "\n\n" + self.format_wishlist(chat_id)
                sent = await self._deliver(chat_id, reply)
                if sent:
                    latest = self.session(chat_id)
                    if latest and (latest.get("version") == version + 1 or latest.get("pending")):
                        self._append_assistant(latest, reply)
                        self.set_session(chat_id, latest)
                if confirmations and not failed:
                    await self.safe_notify(f"Vaca Mágica — lista actualizada (chat {chat_id})\n" + "\n".join(confirmations))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("Vaca worker failed: %s", type(exc).__name__)
        finally:
            if self.tasks.get(chat_id) is asyncio.current_task():
                self.tasks.pop(chat_id, None)

    def maintenance(self) -> None:
        if self.enabled():
            authorized = self.authorized()
            for key, session in self.state().get("sessions", {}).items():
                if key.isdigit() and int(key) in authorized and session.get("pending"):
                    self.ensure_worker(int(key))

    async def close(self) -> None:
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
