"""Authenticated web transport for the existing Telegram applications.

Integration (all on main.py's existing asyncio loop):
    bridge = WebBridge(load_data, save_data, lambda: animal_apps, resolve_actor)
    bot = RecordingExtBot(token=token, bridge=bridge, animal_key=animal_key)
    app = ApplicationBuilder().bot(bot).build()  # existing handlers unchanged
    await bridge.start(host="0.0.0.0", port=port)
    # Call bridge.record_telegram_update(animal_key, update) at animal ingress.
    # await bridge.close() before shutting down the Telegram applications.

CASTORI_WEB_TOKEN is a server-to-server secret, never a browser configuration.
The authenticated proxy supplies X-Castori-Actor; resolve_actor maps it to the
existing numeric identity. This module never trusts IDs supplied by the client.
Only new traffic is mirrored. Existing Telegram history is not imported.
The shared JSON store is written synchronously on the SAME event loop as main.
"""

import asyncio
import copy
import hashlib
import hmac
import json
import logging
import os
import re
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote
from uuid import uuid4

from aiohttp import web
from telegram import Message, Update
from telegram.ext import ExtBot
import unread_notifications as unread
from salchicher_copy import retired_automatic_message


logger = logging.getLogger("control-castora.web")
STORE_KEY = "web_bridge"
MAX_EVENTS = 200
MAX_REQUESTS = 1000
RETENTION_SECONDS = 48 * 60 * 60
CONSULTATION_INACTIVITY_SECONDS = 30 * 24 * 60 * 60
ANIMALS = ("castori", "mimosuga", "salchicher", "vaca", "corte", "dulcimiel")
COMMANDS = {
    "castori": {"start"},
    "mimosuga": {"start", "cuento"},
    "salchicher": {"start", "consulta", "ayuda", "olvidar"},
    "vaca": {"start", "ayuda", "lista", "pedir", "quitar", "favorito", "olvidar"},
    "corte": {"start", "acusar"},
    "dulcimiel": set(),
}
CALLBACK_PREFIXES = {"mimosuga": "cuento:", "corte": "courtdef:", "salchicher": "salchicher:"}
ADMIN_COMMANDS = frozenset({
    "start", "status", "historial", "programar", "programar_mimosuga", "programados", "cancelar",
    "pausar_programas", "reanudar_programas", "mimosuga_auto", "mimosuga_pendientes", "salchicher_auto",
    "vaca_auto", "vaca_ayuda", "vaca_deseos", "vaca_visita", "vaca_visitas",
    "vaca_activar", "vaca_texto", "vaca_hora", "vaca_fecha", "vaca_cancelar", "vaca_pausa",
    "acusar", "alegar", "caso_estado", "admin_ultimos", "admin_ver", "admin_aprobar",
    "admin_descartar", "admin_canon", "admin_lore", "admin_memoria_cuentos",
    "admin_cuento_prueba", "castori", "mimosuga", "corte", "salchicher", "vaca",
})
ADMIN_CALLBACK_PREFIXES = ("adminstory:", "adminteststory:", "autoreply:", "courtdef:")
ADMIN_CURSOR = re.compile(r"^([a-f0-9]{32}):([0-9]{1,16})$")
REQUEST_ID = re.compile(r"^[a-zA-Z0-9_-]{8,100}$")
HISTORY_CURSOR = re.compile(r"^[A-Za-z0-9_-]{1,512}$")
_dispatch_failed = ContextVar("castori_web_dispatch_failed", default=False)
_admin_dispatch_chat = ContextVar("castori_web_admin_chat", default=None)
_UNSPECIFIED_CONSULTATION = object()


def _keyboard(markup) -> list:
    if markup is None:
        return []
    value = markup.to_dict() if hasattr(markup, "to_dict") else markup
    if not isinstance(value, dict):
        return []
    return [
        [{"text": str(button.get("text", ""))[:200], "data": button["callback_data"]}
         for button in row if isinstance(button, dict) and isinstance(button.get("callback_data"), str)]
        for row in value.get("inline_keyboard", []) if isinstance(row, (list, tuple))
    ]


def _markup(buttons: list) -> dict:
    return {"inline_keyboard": [[{"text": b["text"], "callback_data": b["data"]} for b in row] for row in buttons]}


def _failure(code: str, status: int = 400) -> web.Response:
    return web.json_response({"error": code}, status=status, headers={"Cache-Control": "no-store"})


class WebBridge:
    def __init__(self, load: Callable, save: Callable, get_apps: Callable,
                 resolve_actor: Callable, token: str | None = None,
                 allowed_origin: str | None = None, state_provider: Callable | None = None,
                 history_provider=None, get_admin_app: Callable | None = None,
                 admin_state_provider: Callable | None = None, admin_actor_id: Callable | None = None,
                 account_service=None, portal_origin: str | None = None, portal_root=None,
                 get_consultorio: Callable | None = None, admin_access=None,
                 portal_origin_aliases: str | None = None):
        self.load, self.save = load, save
        self.get_apps, self.resolve_actor = get_apps, resolve_actor
        self.token = token if token is not None else os.getenv("CASTORI_WEB_TOKEN", "")
        self.allowed_origin = allowed_origin
        self.state_provider = state_provider
        self.history_provider = history_provider
        self.get_admin_app = get_admin_app or (lambda: None)
        self.admin_state_provider = admin_state_provider
        self.admin_actor_id = admin_actor_id
        self.account_service = account_service
        self.admin_access = admin_access
        self.get_consultorio = get_consultorio or (lambda: None)
        self.portal = None
        if portal_origin:
            from portal import Portal
            try:
                self.portal = Portal(self, account_service, portal_origin, root=portal_root,
                                     aliases=portal_origin_aliases)
            except ValueError:
                logger.warning("Portal desactivado: origen HTTPS no valido")
        # Centralita can contain gifts and consented health notifications. Its
        # display buffer is deliberately never persisted or sent to HistoryService.
        self.admin_events = []
        self.admin_boot = uuid4().hex
        self.admin_sequence = 0
        self.admin_floor = 0
        self.history_lock = asyncio.Lock()
        self.runner = None
        self.tasks: set[asyncio.Task] = set()
        self.locks: dict[int, asyncio.Lock] = {}
        self.observed_apps: set[int] = set()
        self.site = None
        self.maintenance_task = None
        self.push_service = None
        self.push_task = None

    def _read(self) -> tuple[dict, dict]:
        data = copy.deepcopy(self.load())
        state = data.setdefault(STORE_KEY, {"sequence": 0, "inboxes": {}, "requests": {}})
        state.setdefault("sequence", 0)
        state.setdefault("inboxes", {})
        state.setdefault("requests", {})
        state.setdefault("resets", {})
        return data, state

    def eligible(self, chat_id) -> bool:
        return isinstance(chat_id, int) and not isinstance(chat_id, bool) and chat_id > 0 and any(
            self.resolve_actor(actor) == chat_id for actor in ("sandra", "owner"))

    def _actor(self, request) -> tuple[str, int] | None:
        actor = request.headers.get("X-Castori-Actor", "")
        if actor not in {"sandra", "owner"}:
            return None
        chat_id = self.resolve_actor(actor)
        if not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat_id <= 0:
            return None
        return actor, chat_id

    @staticmethod
    def _scope(chat_id: int, animal: str) -> str:
        return f"{chat_id}:{animal}"

    @staticmethod
    def _active_consultation(data: dict, chat_id: int) -> bool:
        session = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {})
        retention = (CONSULTATION_INACTIVITY_SECONDS
                     if session.get("consultation_id") and session.get("retained") is True
                     else RETENTION_SECONDS)
        return bool(session and session.get("updated_at", 0) > time.time() - retention)

    def _clean(self, state: dict, data: dict) -> bool:
        cutoff = time.time() - RETENTION_SECONDS
        changed = False
        for scope, events in state["inboxes"].items():
            if scope.endswith(":salchicher"):
                chat_id = int(scope.split(":", 1)[0])
                active = self._active_consultation(data, chat_id)
                current_id = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {}).get("consultation_id")
                kept = [event for event in events if event.get("timestamp", 0) > cutoff
                        and (not event.get("consultation_id") or (active and event["consultation_id"] == current_id))
                        and (active or not (event.get("requires_consultation") or event.get("role") == "user"))]
                if len(kept) != len(events):
                    state["inboxes"][scope] = kept
                    state["sequence"] += 1
                    state["resets"][scope] = state["sequence"]
                    changed = True
        return changed

    def maintenance(self) -> None:
        self._clean_admin()
        doctor = self.get_consultorio()
        if doctor:
            doctor.maintenance()
        data, state = self._read()
        if self._clean(state, data):
            self.save(data)

    def forget(self, animal: str, chat_id: int, *, forget_unread=True) -> None:
        """Erase only this actor's mirrored conversation, never another session."""
        data, state = self._read()
        if forget_unread:
            unread.forget(data, chat_id, animal)
        state["inboxes"].pop(self._scope(chat_id, animal), None)
        state["sequence"] += 1
        state["resets"][self._scope(chat_id, animal)] = state["sequence"]
        if animal == "vaca":
            scope = self._scope(chat_id, animal)
            forgets = data.setdefault("history_forgets", {})
            epoch = forgets.get(scope, {}).get("epoch", 0) + 1
            forgets[scope] = {"animal": animal, "chat_id": chat_id, "epoch": epoch, "pending": True}
            data.get("history_baseline", {}).get("scopes", {}).pop(scope, None)
            data["history_outbox"] = [item for item in data.get("history_outbox", [])
                                      if (item["animal"], item["chat_id"]) != (animal, chat_id)]
        self.save(data)

    @staticmethod
    def _history_epoch(data: dict, animal: str, chat_id: int) -> int:
        return data.get("history_forgets", {}).get(f"{chat_id}:{animal}", {}).get("epoch", 0)

    def _queue_history(self, data: dict, animal: str, chat_id: int, event: dict) -> None:
        if animal == "salchicher" or self.history_provider is None:
            return
        epoch = self._history_epoch(data, animal, chat_id)
        outbox = data.setdefault("history_outbox", [])
        if not any(item["animal"] == animal and item["chat_id"] == chat_id
                   and item["epoch"] == epoch and item["event"]["id"] == event["id"] for item in outbox):
            outbox.append({"animal": animal, "chat_id": chat_id,
                           "event": copy.deepcopy(event), "epoch": epoch})

    async def flush_history(self) -> None:
        """Commit durable queued records; failed scopes stay queued for a later attempt."""
        if self.history_provider is None:
            return
        async with self.history_lock:
            snapshot = self.load()
            for scope, marker in list(snapshot.get("history_forgets", {}).items()):
                if not marker.get("pending") or marker.get("animal") != "vaca":
                    continue
                try:
                    done = await self.history_provider.forget(marker["animal"], marker["chat_id"], epoch=marker["epoch"])
                except Exception as exc:
                    logger.warning("History forget deferred: %s", type(exc).__name__)
                    continue
                if done:
                    data = self.load()
                    current = data.get("history_forgets", {}).get(scope)
                    if current and current["epoch"] == marker["epoch"]:
                        current["pending"] = False
                        self.save(data)
            snapshot = self.load()
            for item in list(snapshot.get("history_outbox", [])):
                animal, chat_id, epoch = item["animal"], item["chat_id"], item["epoch"]
                current = self.load()
                marker = current.get("history_forgets", {}).get(self._scope(chat_id, animal), {})
                if marker.get("pending"):
                    continue
                if animal == "salchicher" or epoch != self._history_epoch(current, animal, chat_id):
                    done = True
                else:
                    try:
                        done = await self.history_provider.record_event(animal, chat_id, item["event"], epoch=epoch)
                    except Exception as exc:
                        logger.warning("History archive deferred: %s", type(exc).__name__)
                        continue
                if done:
                    # Reload after awaiting: another message or /olvidar may have changed storage.
                    data = self.load()
                    data["history_outbox"] = [queued for queued in data.get("history_outbox", [])
                        if not (queued["animal"] == animal and queued["chat_id"] == chat_id
                                and queued["epoch"] == epoch and queued["event"]["id"] == item["event"]["id"])]
                    self.save(data)

    async def _start_history(self) -> None:
        if self.history_provider is None:
            return
        try:
            # main initializes before polling; this idempotent call also supports standalone use.
            await self.history_provider.initialize()
        except Exception as exc:
            logger.warning("History initialization deferred: %s", type(exc).__name__)
        data, state = self._read()
        for scope, events in state["inboxes"].items():
            identity, animal = scope.split(":", 1)
            chat_id = int(identity)
            if animal in ANIMALS and self.eligible(chat_id):
                for event in events:
                    self._queue_history(data, animal, chat_id, event)
        self.save(data)
        await self.flush_history()

    def record(self, animal: str, chat_id: int, text: str, *, role="assistant",
               source="telegram", message_id=None, reply_markup=None,
               expected_consultation_id=_UNSPECIFIED_CONSULTATION,
               expected_session_id=_UNSPECIFIED_CONSULTATION) -> dict | None:
        if animal not in ANIMALS or not self.eligible(chat_id):
            return None
        data, state = self._read()
        if animal == "salchicher":
            current_session = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {})
            if (expected_consultation_id is not _UNSPECIFIED_CONSULTATION
                    and expected_consultation_id != current_session.get("consultation_id")):
                return None
            if (expected_session_id is not _UNSPECIFIED_CONSULTATION
                    and expected_session_id != current_session.get("session_id")):
                return None
        cleaned = self._clean(state, data)
        consultation_active = animal == "salchicher" and self._active_consultation(data, chat_id)
        if animal == "salchicher" and role == "user" and not consultation_active:
            # The original consultorio does not store health text before consent.
            # Apply that same rule at BOTH Telegram ingress and synthetic web ingress.
            if cleaned:
                self.save(data)
            return None
        scope = self._scope(chat_id, animal)
        events = state["inboxes"].setdefault(scope, [])
        if source == "telegram" and message_id is not None:
            if any(e.get("message_id") == message_id and e["role"] == role for e in events):
                return None
        state["sequence"] += 1
        now = time.time()
        event = {"id": state["sequence"], "revision": state["sequence"], "animal": animal,
                 "role": role, "source": source, "text": str(text)[:16000],
                 "timestamp": now, "time": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                 "buttons": _keyboard(reply_markup)}
        if consultation_active:
            event["requires_consultation"] = True
            consultation_id = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {}).get("consultation_id")
            if consultation_id:
                event["consultation_id"] = consultation_id
        if message_id is not None:
            event["message_id"] = int(message_id)
        events.append(event)
        unread.record(data, chat_id, animal, event)
        if self.push_service is not None:
            try:
                self.push_service.enqueue(data, animal, chat_id, event)
            except Exception as exc:
                logger.warning("Push enqueue unavailable: %s", type(exc).__name__)
        self._queue_history(data, animal, chat_id, event)
        state["inboxes"][scope] = events[-MAX_EVENTS:]
        self.save(data)
        return copy.deepcopy(event)

    def record_telegram_update(self, animal: str, update: Update) -> None:
        """Call only for accepted animal messages; synthetic web updates are skipped."""
        if update.update_id < 0 or not update.message or not update.effective_chat or not update.effective_user:
            return
        if update.effective_chat.type != "private" or update.effective_chat.id != update.effective_user.id:
            return
        if animal in {"castori", "mimosuga", "corte"} and update.effective_chat.id != self.resolve_actor("sandra"):
            return
        text = update.message.text or update.message.caption
        if not text:
            return
        if animal in {"salchicher", "vaca"} and text.split(maxsplit=1)[0].lower().split("@", 1)[0] == "/olvidar":
            self.forget(animal, update.effective_chat.id)
            return
        self.record(animal, update.effective_chat.id, text, role="user", message_id=update.message.message_id)

    def edit_keyboard(self, animal: str, chat_id: int, message_id: int, reply_markup) -> None:
        if animal == "centralita":
            self.edit_admin(chat_id, message_id, reply_markup=reply_markup)
            return
        if not self.eligible(chat_id):
            return
        data, state = self._read()
        for event in state["inboxes"].get(self._scope(chat_id, animal), []):
            if event.get("message_id") == message_id and event["role"] == "assistant":
                state["sequence"] += 1
                event["buttons"] = _keyboard(reply_markup)
                event["revision"] = state["sequence"]
                self.save(data)
                return

    def _is_admin_owner(self, chat_id) -> bool:
        return (isinstance(chat_id, int) and not isinstance(chat_id, bool) and chat_id > 0
                and chat_id == self.resolve_actor("owner"))

    def _editorial_admin_allowed(self) -> bool:
        if self.admin_actor_id is None:
            return False
        try:
            return self._is_admin_owner(self.admin_actor_id())
        except (TypeError, ValueError, RuntimeError):
            return False

    def _clean_admin(self) -> None:
        cutoff = time.time() - RETENTION_SECONDS
        kept = [event for event in self.admin_events if event["timestamp"] > cutoff]
        if len(kept) != len(self.admin_events):
            self.admin_sequence += 1
            self.admin_floor = self.admin_sequence
            self.admin_events = kept

    def record_admin(self, chat_id: int, text: str, *, role="assistant", source="telegram",
                     message_id=None, reply_markup=None, notice=False) -> dict | None:
        if not self._is_admin_owner(chat_id):
            return None
        self._clean_admin()
        if message_id is not None and any(event.get("message_id") == message_id and event["role"] == role
                                          and event["_chat_id"] == chat_id
                                          for event in self.admin_events):
            return None
        self.admin_sequence += 1
        now = time.time()
        event = {"id": self.admin_sequence, "revision": self.admin_sequence, "role": role, "_chat_id": chat_id,
                 "source": source, "text": str(text)[:16000], "timestamp": now,
                 "time": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                 "buttons": _keyboard(reply_markup)}
        if message_id is not None:
            event["message_id"] = int(message_id)
        if notice:
            event["notice"] = True
        self.admin_events.append(event)
        if len(self.admin_events) > MAX_EVENTS:
            self.admin_floor = max(self.admin_floor, self.admin_events[-MAX_EVENTS - 1]["revision"])
            self.admin_events = self.admin_events[-MAX_EVENTS:]
        return copy.deepcopy(event)

    def edit_admin(self, chat_id: int, message_id: int, *, text=None, reply_markup=None) -> None:
        if not self._is_admin_owner(chat_id):
            return
        self._clean_admin()
        for event in self.admin_events:
            if (event.get("message_id") == message_id and event["role"] == "assistant"
                    and event["_chat_id"] == chat_id):
                self.admin_sequence += 1
                if text is not None:
                    event["text"] = str(text)[:16000]
                event["buttons"] = _keyboard(reply_markup)
                event["revision"] = self.admin_sequence
                return
        if text is not None:
            self.record_admin(chat_id, text, message_id=message_id, reply_markup=reply_markup)

    def record_admin_telegram_update(self, update: Update) -> None:
        if (update.update_id < 0 or not update.message or not update.effective_chat or not update.effective_user
                or update.effective_chat.type != "private"
                or update.effective_chat.id != update.effective_user.id
                or not self._is_admin_owner(update.effective_user.id)):
            return
        text = update.message.text or update.message.caption
        if text:
            self.record_admin(update.effective_chat.id, text, role="user", message_id=update.message.message_id)

    def _admin_authorized(self, request) -> bool:
        return request["actor"] == "owner" and self._is_admin_owner(request["chat_id"])

    def _view_identity(self, request):
        """Both people read Sandra's house; only administration keeps the owner scope."""
        if request["actor"] != "owner":
            return request["actor"], request["chat_id"]
        chat_id = self.resolve_actor("sandra")
        if (not isinstance(chat_id, int) or isinstance(chat_id, bool) or chat_id <= 0
                or chat_id == self.resolve_actor("owner")):
            raise web.HTTPServiceUnavailable()
        return "sandra", chat_id

    async def _admin_state(self, request):
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        if request.query:
            return _failure("invalid_admin_query")
        if self.get_admin_app() is None:
            return _failure("centralita_unavailable", 503)
        if self.admin_state_provider is None:
            return _failure("admin_state_unavailable", 503)
        result = self.admin_state_provider()
        if asyncio.iscoroutine(result):
            result = await result
        if not isinstance(result, dict):
            return _failure("admin_state_unavailable", 503)
        editorial_allowed = self._editorial_admin_allowed()
        commands = sorted(command for command in ADMIN_COMMANDS
                          if editorial_allowed or not command.startswith("admin_"))
        return web.json_response({**result, "actor": "owner", "available": True, "commands": commands,
            "editorial_admin": {"available": editorial_allowed,
                                "reason": "" if editorial_allowed else "admin_identity_mismatch"}})

    async def _admin_events(self, request):
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        if set(request.query) - {"after"} or len(request.query.getall("after", [])) > 1:
            return _failure("invalid_admin_query")
        after = request.query.get("after", "0")
        match = ADMIN_CURSOR.fullmatch(after)
        if after != "0" and not match:
            return _failure("invalid_cursor")
        self._clean_admin()
        sequence = int(match[2]) if match else 0
        reset = bool(match and (match[1] != self.admin_boot or sequence < self.admin_floor
                              or sequence > self.admin_sequence))
        visible = [{key: value for key, value in event.items() if key not in {"timestamp", "_chat_id"}}
                   for event in self.admin_events if event["_chat_id"] == request["chat_id"]
                   and (reset or event["revision"] > sequence)]
        return web.json_response({"events": visible, "cursor": f"{self.admin_boot}:{self.admin_sequence}",
                                  "reset": reset})

    async def _admin_body(self, request, allowed):
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return None
        if (not isinstance(body, dict) or set(body) != allowed
                or not isinstance(body.get("request_id"), str) or not REQUEST_ID.fullmatch(body["request_id"])):
            return None
        return body

    async def _admin_action(self, request):
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        body = await self._admin_body(request, {"text", "request_id"})
        if body is None or not isinstance(body["text"], str) or not body["text"].strip() or len(body["text"]) > 4000:
            return _failure("invalid_admin_action")
        body["text"] = body["text"].strip()
        command = self._command(body["text"])
        if command not in ADMIN_COMMANDS:
            return _failure("command_not_allowed", 403)
        if command.startswith("admin_") and not self._editorial_admin_allowed():
            return _failure("admin_identity_mismatch", 403)
        key, fingerprint, existing = self._existing(request["chat_id"], body, "admin_action")
        if existing is not None:
            return existing
        if self.get_admin_app() is None:
            return _failure("centralita_unavailable", 503)
        self._reserve(key, fingerprint, admin=True)
        return self._schedule_admin(request["chat_id"], body, "admin_action", key, self._portal_admin_session(request))

    def _find_admin_callback(self, body):
        self._clean_admin()
        if not isinstance(body.get("data"), str) or not body["data"].startswith(ADMIN_CALLBACK_PREFIXES):
            return None
        if body["data"].startswith(("adminstory:", "adminteststory:")) and not self._editorial_admin_allowed():
            return None
        for event in self.admin_events:
            if (event["id"] == body["event_id"] and event["role"] == "assistant"
                    and event["_chat_id"] == self.resolve_actor("owner") and event.get("message_id") is not None
                    and any(button["data"] == body["data"] for row in event["buttons"] for button in row)):
                return event
        return None

    async def _admin_callback(self, request):
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        body = await self._admin_body(request, {"event_id", "data", "request_id"})
        if body is None or not isinstance(body["event_id"], int) or isinstance(body["event_id"], bool):
            return _failure("invalid_callback")
        key, fingerprint, existing = self._existing(request["chat_id"], body, "admin_callback")
        if existing is not None:
            return existing
        if not self._find_admin_callback(body):
            return _failure("callback_not_allowed", 403)
        if self.get_admin_app() is None:
            return _failure("centralita_unavailable", 503)
        self._reserve(key, fingerprint, admin=True)
        return self._schedule_admin(request["chat_id"], body, "admin_callback", key, self._portal_admin_session(request))

    def _portal_admin_session(self, request):
        # Kept only by the in-flight task, never persisted in a receipt or event.
        return ((self.portal._session_token(request), request["portal_session"]["desk_version"])
                if request.get("portal_owner") is True else None)

    def _schedule_admin(self, chat_id, body, kind, key, portal_session=None):
        task = asyncio.create_task(self._dispatch_admin(chat_id, body, kind, key, portal_session))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return web.json_response({"request_id": body["request_id"], "status": "pending", "duplicate": False}, status=202)

    async def _dispatch_admin(self, chat_id, body, kind, key, portal_session=None):
        status = "uncertain"
        try:
            async with self.locks.setdefault(chat_id, asyncio.Lock()):
                if not self._is_admin_owner(chat_id):
                    status = "rejected"
                    return
                if portal_session is not None:
                    token, version = portal_session
                    live = await self.account_service.get_session(token)
                    if (not live or live["actor"] != "owner" or live["chat_id"] != chat_id
                            or not live.get("desk_expires_at") or live.get("desk_version") != version):
                        status = "rejected"
                        return
                app = self.get_admin_app()
                if app is None:
                    status = "rejected"
                    return
                if id(app) not in self.observed_apps:
                    app.add_error_handler(self._on_application_error)
                    self.observed_apps.add(id(app))
                user = {"id": chat_id, "is_bot": False, "first_name": "Oso"}
                chat = {"id": chat_id, "type": "private", "first_name": "Oso"}
                update_id = -int(uuid4().int % (2**52)) - 1
                payload = {"update_id": update_id}
                if kind == "admin_action":
                    text = body["text"]
                    if self._command(text).startswith("admin_") and not self._editorial_admin_allowed():
                        status = "rejected"
                        return
                    self.record_admin(chat_id, text, role="user", source="web")
                    payload["message"] = {"message_id": abs(update_id), "date": int(time.time()),
                        "chat": chat, "from": user, "text": text,
                        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split(maxsplit=1)[0])}]}
                else:
                    event = self._find_admin_callback(body)
                    if not event:
                        status = "rejected"
                        return
                    payload["callback_query"] = {"id": f"web:{uuid4().hex}", "from": user,
                        "chat_instance": str(chat_id), "data": body["data"], "message": {
                            "message_id": event["message_id"], "date": int(event["timestamp"]), "chat": chat,
                            "from": {"id": app.bot.id, "is_bot": True, "first_name": "Centralita", "username": app.bot.username},
                            "text": event["text"], "reply_markup": _markup(event["buttons"])}}
                marker = _dispatch_failed.set(False)
                admin_marker = _admin_dispatch_chat.set(chat_id)
                try:
                    await app.process_update(Update.de_json(payload, app.bot))
                    status = "uncertain" if _dispatch_failed.get() else "processed"
                finally:
                    _admin_dispatch_chat.reset(admin_marker)
                    _dispatch_failed.reset(marker)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Admin dispatch outcome uncertain: %s", type(exc).__name__)
        finally:
            self._set_status(key, status)

    async def _admin_invitation(self, request):
        return await self._invitation(request, "sandra")

    async def _admin_owner_invitation(self, request):
        return await self._invitation(request, "owner")

    async def _invitation(self, request, actor):
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        if self.account_service is None or self.portal is None:
            return _failure("portal_unavailable", 503)
        from account_service import AccountError
        try:
            if request.query:
                return _failure("invalid_query")
            if request.method == "GET":
                result = await self.account_service.invitation_status(**({"actor": actor} if actor == "owner" else {}))
            else:
                if request.content_type != "application/json":
                    return _failure("json_required", 415)
                try:
                    body = await request.json()
                except (ValueError, UnicodeError):
                    return _failure("invalid_body")
                if (not isinstance(body, dict) or set(body) != {"action"} or not isinstance(body["action"], str)
                        or body["action"] not in {"create", "reset", "revoke"}):
                    return _failure("invalid_body")
                if body["action"] == "revoke":
                    await self.account_service.revoke_invitation(**({"actor": actor} if actor == "owner" else {}))
                    result = await self.account_service.invitation_status(**({"actor": actor} if actor == "owner" else {}))
                else:
                    result = await self.account_service.create_invitation(reset=body["action"] == "reset", **({"actor": actor} if actor == "owner" else {}))
                    fragment = "owner-invite" if actor == "owner" else "invite"
                    result["invite_url"] = self.portal.origin + "/castori/#" + fragment + "/" + quote(result["code"], safe="")
            result["portal_url"] = self.portal.origin + "/castori/"
            if isinstance(result.get("expires_at"), datetime):
                result["expires_at"] = result["expires_at"].isoformat()
            return web.json_response(result)
        except AccountError as exc:
            return _failure(exc.code, exc.status)

    async def _admin_access_status(self, request):
        from admin_access import AdminAccessError
        if request.get("portal_owner") is True and self._admin_authorized(request):
            return await self.account_service.desk_status(self.portal._session_token(request))
        if self.admin_access is None:
            raise AdminAccessError("admin_auth_unavailable", 503)
        if len(request.headers.getall("X-Castori-Owner-Id", [])) != 1:
            raise AdminAccessError("owner_identity_required", 403)
        if len(request.headers.getall("X-Castori-Admin-Session", [])) > 1:
            raise AdminAccessError("admin_locked", 423)
        return await self.admin_access.status(request.headers.get("X-Castori-Owner-Id"),
                                              request.headers.get("X-Castori-Admin-Session"))

    async def _admin_guard(self, request):
        from admin_access import AdminAccessError
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        try:
            status = await self._admin_access_status(request)
            if not status["unlocked"]:
                return _failure("admin_locked", 423)
        except AdminAccessError as exc:
            return _failure(exc.code, exc.status)
        return None

    async def _admin_auth(self, request):
        from admin_access import AdminAccessError
        if not self._admin_authorized(request):
            return _failure("owner_required", 403)
        if request.query:
            return _failure("invalid_admin_query")
        if request.get("portal_owner") is True:
            from account_service import AccountError
            try:
                if request.method == "GET":
                    result = await self._admin_access_status(request)
                elif request.method == "POST":
                    try:
                        body = await request.json()
                    except (ValueError, UnicodeError):
                        return _failure("invalid_admin_auth")
                    if not isinstance(body, dict) or body.get("action") not in ("unlock", "lock"):
                        return _failure("invalid_admin_auth")
                    action = body["action"]
                    if set(body) != ({"action"} if action == "lock" else {"action", "password"}):
                        return _failure("invalid_admin_auth")
                    token = self.portal._session_token(request)
                    result = (await self.account_service.lock_desk(token) if action == "lock"
                              else await self.account_service.unlock_desk(token, body["password"], ip=request.remote or "unknown"))
                else:
                    return _failure("invalid_admin_auth")
                return web.json_response(result, headers={"Cache-Control": "no-store"})
            except AccountError as exc:
                return _failure(exc.code, exc.status)
        try:
            # Validate the trusted identity and storage even for mutations. A
            # missing password never makes any other admin endpoint public.
            result = await self._admin_access_status(request)
            if request.method == "POST":
                if request.content_type != "application/json":
                    return _failure("json_required", 415)
                try:
                    body = await request.json()
                except (ValueError, UnicodeError):
                    return _failure("invalid_body")
                if not isinstance(body, dict) or not isinstance(body.get("action"), str):
                    return _failure("invalid_body")
                action = body["action"]
                if action not in {"setup", "unlock", "lock"} or set(body) != ({"action"} if action == "lock" else {"action", "password"}):
                    return _failure("invalid_body")
                owner = request.headers.get("X-Castori-Owner-Id")
                if action == "lock":
                    result = await self.admin_access.lock(owner, request.headers.get("X-Castori-Admin-Session"))
                else:
                    method = self.admin_access.setup if action == "setup" else self.admin_access.unlock
                    result = await method(owner, body["password"])
            return web.json_response(result, headers={"Cache-Control": "no-store"})
        except AdminAccessError as exc:
            return _failure(exc.code, exc.status)

    def create_app(self) -> web.Application:
        @web.middleware
        async def authentication(request, handler):
            if self.portal and self.portal.handles(request):
                return await self.portal.authenticate(request, handler)
            if request.path == "/castori-web/health" and request.method == "GET":
                return await handler(request)
            supplied = request.headers.get("Authorization", "")
            expected = f"Bearer {self.token}"
            if not self.token or not hmac.compare_digest(supplied.encode(), expected.encode()):
                return _failure("unauthorized", 401)
            origin = request.headers.get("Origin")
            if origin and (not self.allowed_origin or origin != self.allowed_origin):
                return _failure("origin_not_allowed", 403)
            actor = self._actor(request)
            if not actor:
                return _failure("actor_unavailable", 403)
            request["actor"], request["chat_id"] = actor
            if (request["actor"] == "owner" and request.method == "POST"
                    and request.path in {"/castori-web/" + name for name in
                        ("message", "callback", "consultation-action", "consultation-message")}):
                return _failure("read_only", 403)
            try:
                if request.path.startswith("/castori-web/admin-"):
                    if not self._admin_authorized(request):
                        return _failure("owner_required", 403)
                    if request.path != "/castori-web/admin-auth":
                        denied = await self._admin_guard(request)
                        if denied is not None:
                            return denied
                response = await handler(request)
                response.headers["Cache-Control"] = "no-store"
                return response
            except web.HTTPException:
                raise
            except Exception as exc:
                logger.warning("Web bridge request failed: %s", type(exc).__name__)
                return _failure("temporarily_unavailable", 503)

        app = web.Application(middlewares=[authentication], client_max_size=24000)
        app.router.add_get("/castori-web/health", self._health)
        app.router.add_get("/castori-web/state", self._state)
        app.router.add_get("/castori-web/events", self._events)
        app.router.add_post("/castori-web/read", self._mark_read)
        app.router.add_get("/castori-web/request", self._request_status)
        app.router.add_post("/castori-web/message", self._message)
        app.router.add_post("/castori-web/callback", self._callback)
        app.router.add_get("/castori-web/history", self._history)
        app.router.add_get("/castori-web/stories", self._stories)
        app.router.add_get("/castori-web/story", self._story)
        app.router.add_get("/castori-web/consultations", self._consultations)
        app.router.add_get("/castori-web/consultation", self._consultation)
        app.router.add_post("/castori-web/consultation-action", self._consultation_action)
        app.router.add_post("/castori-web/consultation-message", self._consultation_message)
        app.router.add_get("/castori-web/admin-auth", self._admin_auth)
        app.router.add_post("/castori-web/admin-auth", self._admin_auth)
        app.router.add_get("/castori-web/admin-state", self._admin_state)
        app.router.add_get("/castori-web/admin-events", self._admin_events)
        app.router.add_post("/castori-web/admin-action", self._admin_action)
        app.router.add_post("/castori-web/admin-callback", self._admin_callback)
        app.router.add_get("/castori-web/admin-invitation", self._admin_invitation)
        app.router.add_post("/castori-web/admin-invitation", self._admin_invitation)
        app.router.add_get("/castori-web/admin-owner-invitation", self._admin_owner_invitation)
        app.router.add_post("/castori-web/admin-owner-invitation", self._admin_owner_invitation)
        if self.portal:
            self.portal.install(app)
        return app

    async def start(self, host="127.0.0.1", port=8080) -> None:
        if not self.token or len(self.token) < 32:
            raise ValueError("CASTORI_WEB_TOKEN must contain at least 32 characters")
        data, state = self._read()
        unread.initialize(data)
        self._clean(state, data)
        for receipt in state["requests"].values():
            if receipt["status"] == "pending":
                receipt["status"] = "uncertain"
        self.save(data)
        await self._start_history()
        self.runner = web.AppRunner(self.create_app(), access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, host, port)
        await self.site.start()
        self.maintenance_task = asyncio.create_task(self._maintenance_loop())
        if self.push_service is not None:
            self.push_task = asyncio.create_task(self._push_loop())

    async def _push_loop(self):
        while True:
            await asyncio.sleep(2)
            try:
                await self.push_service.tick()
            except Exception as exc:
                logger.warning("Push delivery unavailable: %s", type(exc).__name__)

    async def _maintenance_loop(self):
        while True:
            await asyncio.sleep(60)
            try:
                self.maintenance()
                await self.flush_history()
            except Exception as exc:
                logger.warning("Web retention cleanup failed: %s", type(exc).__name__)

    async def close(self) -> None:
        if self.push_task:
            self.push_task.cancel()
            await asyncio.gather(self.push_task, return_exceptions=True)
            self.push_task = None
        if self.maintenance_task:
            self.maintenance_task.cancel()
            await asyncio.gather(self.maintenance_task, return_exceptions=True)
            self.maintenance_task = None
        if self.runner:
            await self.runner.cleanup()
            self.runner = None
        for task in list(self.tasks):
            task.cancel()
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
        self.tasks.clear()
        self.admin_events.clear()
        self.admin_boot = uuid4().hex
        self.admin_sequence = self.admin_floor = 0
        if self.history_provider is not None:
            try:
                await asyncio.wait_for(self.flush_history(), timeout=10)
            except Exception as exc:
                logger.warning("History shutdown flush deferred: %s", type(exc).__name__)

    async def _health(self, request):
        return web.json_response({"ok": True}, headers={"Cache-Control": "no-store"})

    async def _state(self, request):
        self.maintenance()
        data = self.load()
        apps = self.get_apps()
        view_actor, chat_id = self._view_identity(request)
        read_only = request["actor"] == "owner"
        mimosuga = data.get("auto_replies", {}).get("mimosuga", {})
        characters = []
        for animal in ANIMALS:
            mode = "manual" if animal == "castori" else "automatic"
            if animal == "mimosuga":
                mode = mimosuga.get("mode", "review") if mimosuga.get("enabled", False) else "manual"
            if animal in {"vaca", "salchicher"} and not data.get(animal, {}).get("enabled", True):
                mode = "paused"
            characters.append({"id": animal, "available": animal in apps,
                               "mode": mode, "commands": [] if read_only else sorted(COMMANDS[animal]),
                               "reason": "animal_unavailable" if animal not in apps else ""})
        wishes = data.get("vaca", {}).get("sessions", {}).get(str(chat_id), {}).get("wishes", [])
        public_wishes = [{key: item.get(key, False if key == "favorite" else "")
                          for key in ("id", "name", "details", "url", "favorite")}
                         for item in wishes[:60] if isinstance(item, dict)]
        consultation = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {})
        active = self._active_consultation(data, chat_id)
        result = {"actor": request["actor"], "read_only": read_only, "characters": characters, "wishes": public_wishes,
                  "unread": unread.summary(data, chat_id),
                  "private_consultation": {"active": active, "sharing": active},
                  "shared_between_users": True,
                  "history": {"enabled": self.history_provider is not None, "excluded_animals": ["salchicher"]},
                  "stories": {"enabled": self.history_provider is not None}}
        doctor = self.get_consultorio()
        current = doctor.active_consultation(chat_id) if doctor else None
        result["consultorio"] = {"available": doctor is not None and "salchicher" in apps,
                                 "active_id": current["id"] if current else None}
        # Optional provider must itself return an explicit public projection, not load_data().
        if self.state_provider:
            extra = self.state_provider(view_actor, chat_id)
            if asyncio.iscoroutine(extra):
                extra = await extra
            if isinstance(extra, dict):
                result["details"] = extra
        return web.json_response(result)

    async def _consultations(self, request):
        if request.query:
            return _failure("invalid_consultation_query")
        doctor = self.get_consultorio()
        if doctor is None:
            return _failure("consultorio_unavailable", 503)
        _, chat_id = self._view_identity(request)
        consultations = doctor.list_consultations(chat_id)
        active = next((entry["id"] for entry in consultations if entry["status"] == "active"), None)
        return web.json_response({"consultations": consultations, "active_id": active})

    @staticmethod
    def _consultation_id(value):
        return isinstance(value, str) and REQUEST_ID.fullmatch(value) is not None

    async def _consultation(self, request):
        if (set(request.query) != {"id"} or len(request.query.getall("id")) != 1
                or not self._consultation_id(request.query["id"])):
            return _failure("invalid_consultation_query")
        doctor = self.get_consultorio()
        if doctor is None:
            return _failure("consultorio_unavailable", 503)
        _, chat_id = self._view_identity(request)
        item = doctor.get_consultation(chat_id, request.query["id"])
        cursor = unread.latest(self.load(), chat_id, "salchicher", request.query["id"])
        return web.json_response({"consultation": item, "read_cursor": cursor}) if item else _failure("consultation_not_found", 404)

    async def _consultation_action(self, request):
        if request.query:
            return _failure("invalid_consultation_action")
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return _failure("invalid_consultation_action")
        if not isinstance(body, dict):
            return _failure("invalid_consultation_action")
        action = body.get("action")
        if not isinstance(action, str):
            return _failure("invalid_consultation_action")
        if action == "start":
            if set(body) != {"action", "retain_history"} or type(body["retain_history"]) is not bool:
                return _failure("invalid_consultation_action")
        elif action in {"close", "delete"}:
            if set(body) != {"action", "consultation_id"} or not self._consultation_id(body["consultation_id"]):
                return _failure("invalid_consultation_action")
        else:
            return _failure("invalid_consultation_action")
        doctor = self.get_consultorio()
        if doctor is None:
            return _failure("consultorio_unavailable", 503)
        chat_id = request["chat_id"]
        async with self.locks.setdefault(chat_id, asyncio.Lock()):
            if action == "start":
                if "salchicher" not in self.get_apps() or not doctor.enabled():
                    return _failure("consultorio_unavailable", 503)
                try:
                    item = doctor.start_consultation(chat_id, retain_history=body["retain_history"])
                except ValueError as exc:
                    if str(exc) == "consultation_active":
                        return _failure("consultation_active", 409)
                    raise
                # Reset episode content, including legacy consent prompts, while
                # keeping general letters delivered outside any consultation.
                data, state = self._read()
                scope = self._scope(chat_id, "salchicher")
                events = state["inboxes"].get(scope, [])
                general = [event for event in events if event.get("role") == "assistant"
                           and not event.get("consultation_id") and not event.get("requires_consultation")
                           and not event.get("buttons")]
                if len(general) != len(events):
                    state["inboxes"][scope] = general
                    state["sequence"] += 1
                    state["resets"][scope] = state["sequence"]
                    self.save(data)
                for message in item.get("messages", []):
                    if message.get("role") == "assistant":
                        self.record("salchicher", chat_id, message["content"], source="web")
                return web.json_response({"consultation": item})
            item = doctor.get_consultation(chat_id, body["consultation_id"])
            if item is None:
                return _failure("consultation_not_found", 404)
            if action == "close":
                result = doctor.close_consultation(chat_id, body["consultation_id"])
            else:
                doctor.delete_consultation(chat_id, body["consultation_id"])
                result = None
            self.maintenance()
            response = {"consultation": result}
            if action == "delete":
                response["deleted"] = True
            return web.json_response(response)

    async def _consultation_message(self, request):
        if request.query:
            return _failure("invalid_consultation_message")
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return _failure("invalid_consultation_message")
        if (not isinstance(body, dict) or set(body) != {"consultation_id", "text", "request_id"}
                or not self._consultation_id(body.get("consultation_id"))
                or not isinstance(body.get("text"), str) or not body["text"].strip()
                or len(body["text"]) > 4000
                or not isinstance(body.get("request_id"), str) or not REQUEST_ID.fullmatch(body["request_id"])):
            return _failure("invalid_consultation_message")
        body["text"] = body["text"].strip()
        if self._command(body["text"]) is not None:
            return _failure("command_not_allowed", 403)
        body["animal"] = "salchicher"
        key, fingerprint, existing = self._existing(request["chat_id"], body, "consultation-message")
        if existing is not None:
            return existing
        doctor = self.get_consultorio()
        if doctor is None or "salchicher" not in self.get_apps():
            return _failure("consultorio_unavailable", 503)
        active = doctor.active_consultation(request["chat_id"])
        if active is None or active["id"] != body["consultation_id"]:
            return _failure("consultation_required", 409)
        self._reserve(key, fingerprint)
        return self._schedule(request["chat_id"], body, "consultation-message", key)

    @staticmethod
    def _page_arguments(request, *, animal=False, default_limit=40, max_limit=100):
        allowed = {"before", "limit"} | ({"animal"} if animal else set())
        if set(request.query) - allowed or any(len(request.query.getall(key)) != 1 for key in request.query):
            raise ValueError("Invalid query")
        if animal and request.query.get("animal") not in ANIMALS:
            raise ValueError("Invalid animal")
        limit_text = request.query.get("limit", str(default_limit))
        if not re.fullmatch(r"[1-9][0-9]{0,2}", limit_text):
            raise ValueError("Invalid limit")
        limit = int(limit_text)
        if limit > max_limit:
            raise ValueError("Invalid limit")
        before = request.query.get("before")
        if before is not None and not HISTORY_CURSOR.fullmatch(before):
            raise ValueError("Invalid cursor")
        return before, limit

    async def _history(self, request):
        try:
            before, limit = self._page_arguments(request, animal=True)
        except ValueError:
            return _failure("invalid_history_query")
        animal = request.query["animal"]
        if animal == "salchicher":
            return _failure("private_consultation_not_archived", 403)
        if self.history_provider is None:
            return _failure("history_unavailable", 503)
        try:
            view_actor, chat_id = self._view_identity(request)
            result = await self.history_provider.page(view_actor, chat_id, animal,
                                                       before=before, limit=limit)
        except ValueError:
            return _failure("invalid_cursor")
        except Exception as exc:
            logger.warning("History read unavailable: %s", type(exc).__name__)
            return _failure("history_unavailable", 503)
        if result.get("archive_available") is False and not result.get("messages"):
            return _failure("history_unavailable", 503)
        return web.json_response(result)

    async def _stories(self, request):
        try:
            before, limit = self._page_arguments(request, default_limit=12, max_limit=50)
        except ValueError:
            return _failure("invalid_stories_query")
        if self.history_provider is None:
            return _failure("stories_unavailable", 503)
        try:
            view_actor, chat_id = self._view_identity(request)
            result = await self.history_provider.stories(view_actor, chat_id, before=before, limit=limit)
        except ValueError:
            return _failure("invalid_cursor")
        except Exception as exc:
            logger.warning("Stories read unavailable: %s", type(exc).__name__)
            return _failure("stories_unavailable", 503)
        return web.json_response(result)

    async def _story(self, request):
        if set(request.query) != {"id"} or len(request.query.getall("id")) != 1:
            return _failure("invalid_story_id")
        raw_id = request.query["id"]
        if not re.fullmatch(r"[1-9][0-9]{0,18}", raw_id) or int(raw_id) > 2**63 - 1:
            return _failure("invalid_story_id")
        if self.history_provider is None:
            return _failure("stories_unavailable", 503)
        try:
            view_actor, chat_id = self._view_identity(request)
            result = await self.history_provider.story(view_actor, chat_id, int(raw_id))
        except Exception as exc:
            logger.warning("Story read unavailable: %s", type(exc).__name__)
            return _failure("stories_unavailable", 503)
        return web.json_response(result) if result is not None else _failure("story_not_found", 404)

    async def _events(self, request):
        animal = request.query.get("animal", "")
        if animal not in ANIMALS:
            return _failure("unknown_animal")
        try:
            after = int(request.query.get("after", "0"))
            if after < 0:
                raise ValueError()
        except ValueError:
            return _failure("invalid_cursor")
        data, state = self._read()
        if self._clean(state, data):
            self.save(data)
        _, chat_id = self._view_identity(request)
        scope = self._scope(chat_id, animal)
        events = state["inboxes"].get(scope, [])
        reset = state["resets"].get(scope, 0) > after
        visible = [{key: value for key, value in event.items() if key not in {"timestamp", "requires_consultation"}}
                   for event in events if (reset or event.get("revision", event["id"]) > after)
                   and not (animal == "salchicher" and retired_automatic_message(event))]
        return web.json_response({"events": visible, "cursor": state["sequence"], "reset": reset,
                                  "unread": unread.summary(data, chat_id)})

    async def _mark_read(self, request):
        # Reading the shared house as Miguel must never consume Sandra's mail.
        if request["actor"] != "sandra":
            return _failure("read_only", 403)
        if request.query:
            return _failure("invalid_read")
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return _failure("invalid_read")
        if (not isinstance(body, dict)
                or set(body) != {"animal", "event_id", "consultation_id"}
                or body.get("animal") not in ANIMALS
                or type(body.get("event_id")) is not int
                or body["event_id"] <= 0
                or (body["consultation_id"] is not None
                    and not self._consultation_id(body["consultation_id"]))):
            return _failure("invalid_read")
        data, _ = self._read()
        if not unread.acknowledge(data, request["chat_id"], body["animal"],
                                  body["event_id"], body["consultation_id"]):
            return _failure("invalid_read")
        self.save(data)
        return web.json_response({"ok": True, "unread": unread.summary(data, request["chat_id"])})

    def _push_authorized(self, request):
        return (bool(request.get("portal_session")) and request.get("actor") == "sandra"
                and request.get("chat_id") == self.resolve_actor("sandra")
                and request.get("chat_id") != self.resolve_actor("owner"))

    async def _push_status(self, request):
        if request.query:
            return _failure("invalid_push_request")
        if not self._push_authorized(request) or self.push_service is None:
            return web.json_response({"available": False, "public_key": None, "subscribed": False, "device_count": 0})
        return web.json_response(self.push_service.status(request["chat_id"]))

    async def _push_mutation(self, request, *, subscribe):
        if not self._push_authorized(request):
            return _failure("read_only", 403)
        if request.query:
            return _failure("invalid_push_request")
        if self.push_service is None:
            return _failure("push_unavailable", 503)
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return _failure("invalid_push_request")
        field = "subscription" if subscribe else "endpoint"
        if not isinstance(body, dict) or set(body) != {field}:
            return _failure("invalid_push_request")
        from web_push import WebPushError
        try:
            result = (self.push_service.subscribe(request["chat_id"], body[field]) if subscribe
                      else self.push_service.unsubscribe(request["chat_id"], body[field]))
        except WebPushError as exc:
            return _failure(exc.code, exc.status)
        return web.json_response(result)

    async def _push_subscribe(self, request):
        return await self._push_mutation(request, subscribe=True)

    async def _push_unsubscribe(self, request):
        return await self._push_mutation(request, subscribe=False)

    async def _request_status(self, request):
        request_id = request.query.get("request_id", "")
        if not REQUEST_ID.fullmatch(request_id):
            return _failure("invalid_request_id")
        _, state = self._read()
        receipt = state["requests"].get(f"{request['chat_id']}:{request_id}")
        if not receipt:
            return _failure("request_not_found", 404)
        if receipt.get("admin"):
            denied = await self._admin_guard(request)
            if denied is not None:
                return denied
        return web.json_response(self._receipt_result(request_id, receipt))

    @staticmethod
    def _receipt_result(request_id: str, receipt: dict) -> dict:
        result = {"request_id": request_id, "status": receipt["status"]}
        # A fixed UI notice survives deletion of a temporary episode. It carries
        # neither the user's symptoms nor a copy of the consultation.
        if receipt.get("notice") == "urgent_help":
            result["notice"] = "urgent_help"
        return result

    async def _body(self, request, allowed: set):
        try:
            body = await request.json()
        except (ValueError, UnicodeError):
            return None
        if not isinstance(body, dict) or set(body) != allowed:
            return None
        if not isinstance(body.get("animal"), str) or body["animal"] not in COMMANDS or not isinstance(body.get("request_id"), str):
            return None
        if not REQUEST_ID.fullmatch(body["request_id"]):
            return None
        return body

    def _existing(self, chat_id: int, body: dict, kind: str):
        key = f"{chat_id}:{body['request_id']}"
        fingerprint = hashlib.sha256(json.dumps({"kind": kind, **body}, sort_keys=True).encode()).hexdigest()
        _, state = self._read()
        existing = state["requests"].get(key)
        if existing and existing["fingerprint"] != fingerprint:
            return key, fingerprint, _failure("request_id_conflict", 409)
        if existing:
            return key, fingerprint, web.json_response({
                **self._receipt_result(body["request_id"], existing), "duplicate": True})
        return key, fingerprint, None

    def _reserve(self, key: str, fingerprint: str, *, admin=False) -> None:
        data, state = self._read()
        state["requests"][key] = {"fingerprint": fingerprint, "status": "pending", "at": time.time()}
        if admin:
            state["requests"][key]["admin"] = True
        # Keep recent idempotency receipts; they never contain user messages or symptoms.
        if len(state["requests"]) > MAX_REQUESTS:
            completed = [k for k, v in state["requests"].items() if v["status"] != "pending"]
            for old in completed[:len(state["requests"]) - MAX_REQUESTS]:
                state["requests"].pop(old, None)
        self.save(data)

    def _set_status(self, key: str, status: str, *, notice=None) -> None:
        data, state = self._read()
        if key in state["requests"]:
            state["requests"][key]["status"] = status
            if notice == "urgent_help":
                state["requests"][key]["notice"] = "urgent_help"
            self.save(data)

    def _schedule(self, chat_id: int, body: dict, kind: str, key: str) -> web.Response:
        task = asyncio.create_task(self._dispatch(chat_id, body, kind, key))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return web.json_response({"request_id": body["request_id"], "status": "pending", "duplicate": False}, status=202)

    async def _message(self, request):
        body = await self._body(request, {"animal", "text", "request_id"})
        if body is None or not isinstance(body["text"], str) or not body["text"].strip() or len(body["text"]) > 4000:
            return _failure("invalid_message")
        body["text"] = body["text"].strip()
        command = self._command(body["text"])
        if command is not None and command not in COMMANDS[body["animal"]]:
            return _failure("command_not_allowed", 403)
        if body["animal"] not in self.get_apps():
            return _failure("animal_unavailable", 503)
        if body["animal"] == "salchicher" and command not in {"ayuda", "olvidar"}:
            return _failure("consultation_required", 409)
        # /start for the owner would rebind legacy Castori/Mimosuga/Corte identities.
        if request["actor"] == "owner" and body["animal"] in {"castori", "mimosuga", "corte"}:
            return _failure("actor_not_supported", 403)
        key, fingerprint, existing = self._existing(request["chat_id"], body, "message")
        if existing is not None:
            return existing
        self._reserve(key, fingerprint)
        return self._schedule(request["chat_id"], body, "message", key)

    @staticmethod
    def _command(text: str) -> str | None:
        if not text.startswith("/"):
            return None
        first = text.split(maxsplit=1)[0]
        # Disallow cross-bot mentions and malformed command names entirely.
        return first[1:] if re.fullmatch(r"/[a-z_]+", first) else "__invalid__"

    def _find_callback(self, chat_id: int, body: dict) -> dict | None:
        prefix = CALLBACK_PREFIXES.get(body["animal"])
        if not prefix or not isinstance(body.get("data"), str) or not body["data"].startswith(prefix):
            return None
        data, state = self._read()
        if self._clean(state, data):
            self.save(data)
        for event in state["inboxes"].get(self._scope(chat_id, body["animal"]), []):
            if (event["id"] == body["event_id"] and event["role"] == "assistant"
                    and event.get("message_id") is not None
                    and any(button["data"] == body["data"] for row in event["buttons"] for button in row)):
                return event
        return None

    async def _callback(self, request):
        body = await self._body(request, {"animal", "event_id", "data", "request_id"})
        if body is None or not isinstance(body["event_id"], int) or isinstance(body["event_id"], bool):
            return _failure("invalid_callback")
        if body["animal"] == "salchicher":
            return _failure("consultation_action_required", 403)
        if request["actor"] == "owner" and body["animal"] in {"castori", "mimosuga", "corte"}:
            return _failure("actor_not_supported", 403)
        key, fingerprint, existing = self._existing(request["chat_id"], body, "callback")
        if existing is not None:
            return existing
        if not self._find_callback(request["chat_id"], body):
            return _failure("callback_not_allowed", 403)
        if body["animal"] not in self.get_apps():
            return _failure("animal_unavailable", 503)
        self._reserve(key, fingerprint)
        return self._schedule(request["chat_id"], body, "callback", key)

    async def _on_application_error(self, update, context):
        if isinstance(update, Update) and update.update_id < 0:
            _dispatch_failed.set(True)

    async def _dispatch(self, chat_id: int, body: dict, kind: str, key: str) -> None:
        status = "uncertain"
        urgent_candidate = False
        retained = False
        try:
            async with self.locks.setdefault(chat_id, asyncio.Lock()):
                if kind == "consultation-message":
                    doctor = self.get_consultorio()
                    active = doctor.active_consultation(chat_id) if doctor else None
                    if active is None or active["id"] != body["consultation_id"]:
                        status = "rejected"
                        return
                    from salchicher_service import urgent_signal
                    urgent_candidate = urgent_signal(body["text"])
                    retained = active.get("retained") is True
                app = self.get_apps()[body["animal"]]
                if id(app) not in self.observed_apps and hasattr(app, "add_error_handler"):
                    app.add_error_handler(self._on_application_error)
                    self.observed_apps.add(id(app))
                user = {"id": chat_id, "is_bot": False, "first_name": "Patita"}
                chat = {"id": chat_id, "type": "private", "first_name": "Patita"}
                update_id = -int(uuid4().int % (2**52)) - 1
                payload = {"update_id": update_id}
                if kind in {"message", "consultation-message"}:
                    text = body["text"]
                    if self._command(text) == "olvidar":
                        self.forget(body["animal"], chat_id)
                    else:
                        self.record(body["animal"], chat_id, text, role="user", source="web")
                    message = {"message_id": abs(update_id), "date": int(time.time()),
                               "chat": chat, "from": user, "text": text}
                    if self._command(text):
                        message["entities"] = [{"type": "bot_command", "offset": 0,
                                                "length": len(text.split(maxsplit=1)[0])}]
                    payload["message"] = message
                else:
                    event = self._find_callback(chat_id, body)
                    if not event:
                        status = "rejected"
                        return
                    bot_user = {"id": app.bot.id, "is_bot": True,
                                "first_name": "Castori", "username": app.bot.username}
                    message = {"message_id": event["message_id"], "date": int(event["timestamp"]),
                               "chat": chat, "from": bot_user, "text": event["text"],
                               "reply_markup": _markup(event["buttons"])}
                    payload["callback_query"] = {"id": f"web:{uuid4().hex}", "from": user,
                                                 "chat_instance": str(chat_id), "message": message, "data": body["data"]}
                marker = _dispatch_failed.set(False)
                try:
                    await app.process_update(Update.de_json(payload, app.bot))
                    status = "uncertain" if _dispatch_failed.get() else "processed"
                finally:
                    _dispatch_failed.reset(marker)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Web dispatch outcome uncertain: %s", type(exc).__name__)
        finally:
            notice = None
            if urgent_candidate:
                doctor_state = self.load().get("salchicher", {})
                current = doctor_state.get("sessions", {}).get(str(chat_id), {})
                record = doctor_state.get("consultations", {}).get(str(chat_id), {}).get(body["consultation_id"])
                closed = current.get("consultation_id") != body["consultation_id"]
                if closed and ((record or {}).get("closure_reason") == "urgent_help" or not retained):
                    notice = "urgent_help"
                    # Even a failed Telegram send must not leave the deleted
                    # temporary episode's user text in the transient mirror.
                    self.maintenance()
            self._set_status(key, status, notice=notice)


class RecordingExtBot(ExtBot):
    """Animal delivery to the portal, with a separate Telegram notification lane."""
    __slots__ = ("_web_bridge", "_web_animal")

    def __init__(self, *, token: str, bridge: WebBridge, animal_key: str, **kwargs):
        super().__init__(token=token, **kwargs)
        object.__setattr__(self, "_web_bridge", bridge)
        object.__setattr__(self, "_web_animal", animal_key)

    def _portal_delivery(self, chat_id):
        return (self._web_animal in ANIMALS and self._web_bridge.portal is not None
                and os.getenv("CASTORI_WEB_ONLY_DELIVERY", "true").lower() == "true"
                and type(chat_id) is int and chat_id > 0
                and chat_id == self._web_bridge.resolve_actor("sandra")
                and chat_id != self._web_bridge.resolve_actor("owner"))

    def _portal_message(self, chat_id, event, reply_markup=None):
        # Negative IDs can never be mistaken for an actual Telegram delivery.
        return Message.de_json({"message_id": event["message_id"],
            "date": int(event["timestamp"]), "chat": {"id": chat_id, "type": "private"},
            "from": {"id": self.id, "is_bot": True, "first_name": self.first_name,
                     "username": self.username}, "text": event["text"],
            "reply_markup": reply_markup.to_dict() if hasattr(reply_markup, "to_dict") else reply_markup}, self)

    async def send_notification(self, chat_id, text, **kwargs):
        """Send one generic reminder without creating another unread event."""
        if (self._web_animal != "castori" or chat_id != self._web_bridge.resolve_actor("sandra")
                or chat_id == self._web_bridge.resolve_actor("owner")):
            raise ValueError("notification_recipient_unavailable")
        return await super().send_message(chat_id, text, **kwargs)

    async def send_chat_action(self, chat_id, action, *args, **kwargs):
        if self._portal_delivery(chat_id):
            return True
        return await super().send_chat_action(chat_id, action, *args, **kwargs)

    async def send_message(self, chat_id, text, *args, **kwargs):
        consultation_id = session_id = _UNSPECIFIED_CONSULTATION
        if self._web_animal == "salchicher":
            session = self._web_bridge.load().get("salchicher", {}).get("sessions", {}).get(str(chat_id), {})
            consultation_id, session_id = session.get("consultation_id"), session.get("session_id")
        if self._portal_delivery(chat_id):
            # record() durably writes before reporting success to existing handlers.
            # Never fall back to Telegram on a failed portal write.
            _, state = self._web_bridge._read()
            markup = kwargs.get("reply_markup")
            event = self._web_bridge.record(self._web_animal, chat_id, text, source="web",
                message_id=-(state["sequence"] + 1), reply_markup=markup,
                expected_consultation_id=consultation_id, expected_session_id=session_id)
            if event is None:
                raise RuntimeError("portal_delivery_unavailable")
            return self._portal_message(chat_id, event, markup)
        result = await super().send_message(chat_id, text, *args, **kwargs)
        try:
            if self._web_animal == "centralita":
                self._web_bridge.record_admin(result.chat_id, result.text or text,
                    message_id=result.message_id, reply_markup=result.reply_markup)
            else:
                self._web_bridge.record(self._web_animal, result.chat_id, result.text or text,
                                        message_id=result.message_id, reply_markup=result.reply_markup,
                                        expected_consultation_id=consultation_id, expected_session_id=session_id)
        except Exception as exc:
            # Mirroring failure cannot turn a successful Telegram send into a retry.
            logger.warning("Web mirror failed after Telegram delivery: %s", type(exc).__name__)
        return result

    async def edit_message_text(self, *args, **kwargs):
        result = await super().edit_message_text(*args, **kwargs)
        if self._web_animal == "centralita":
            try:
                if hasattr(result, "chat_id"):
                    self._web_bridge.edit_admin(result.chat_id, result.message_id,
                        text=result.text, reply_markup=result.reply_markup)
            except Exception as exc:
                logger.warning("Admin text mirror failed: %s", type(exc).__name__)
        return result

    async def edit_message_reply_markup(self, *args, **kwargs):
        chat_id = kwargs.get("chat_id", args[0] if args else None)
        message_id = kwargs.get("message_id", args[1] if len(args) > 1 else None)
        if type(message_id) is int and message_id < 0:
            if not self._portal_delivery(chat_id):
                raise ValueError("invalid_portal_message")
            markup = kwargs.get("reply_markup")
            self._web_bridge.edit_keyboard(self._web_animal, chat_id, message_id, markup)
            _, state = self._web_bridge._read()
            event = next((e for e in state["inboxes"].get(f"{chat_id}:{self._web_animal}", [])
                          if e.get("message_id") == message_id and e["role"] == "assistant"), None)
            if event is None:
                raise ValueError("portal_message_not_found")
            return self._portal_message(chat_id, event, markup)
        result = await super().edit_message_reply_markup(*args, **kwargs)
        try:
            if hasattr(result, "chat_id"):
                self._web_bridge.edit_keyboard(self._web_animal, result.chat_id,
                                               result.message_id, result.reply_markup)
        except Exception as exc:
            logger.warning("Web keyboard mirror failed: %s", type(exc).__name__)
        return result

    async def answer_callback_query(self, callback_query_id, *args, **kwargs):
        if isinstance(callback_query_id, str) and callback_query_id.startswith("web:"):
            text = kwargs.get("text", args[0] if args else None)
            chat_id = _admin_dispatch_chat.get()
            if self._web_animal == "centralita" and text and chat_id:
                self._web_bridge.record_admin(chat_id, text, source="web", notice=True)
            return True
        return await super().answer_callback_query(callback_query_id, *args, **kwargs)
