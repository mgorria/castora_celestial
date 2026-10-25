"""Private read cursors and twice-daily Telegram notices for Sandra's web inbox.

The ledger contains identifiers and timestamps only. Call initialize before new
traffic is accepted, then record inside the bridge's existing atomic save.
All storage access runs synchronously on the application's single event loop.
"""

import asyncio
import copy
import logging
import time
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from salchicher_copy import retired_automatic_message


logger = logging.getLogger("control-castora.notifications")
STORE_KEY = "unread_notifications"
ANIMALS = frozenset(("castori", "mimosuga", "salchicher", "vaca", "corte", "dulcimiel"))
DEFAULT_SCOPE = "_"
NOTICE_TEXT = ("🦫 Oficina Castori\n\nPatita, tienes mensajes sin leer en la oficina. "
               "Tus animales te han dejado unas cartas. 💌")


def _positive_id(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _scope(chat_id, animal):
    return f"{chat_id}:{animal}"


def _consultation(animal, event):
    value = event.get("consultation_id") if animal == "salchicher" else None
    return value if isinstance(value, str) and value else DEFAULT_SCOPE


def _state(data):
    return data.setdefault(STORE_KEY, {"version": 1, "scopes": {}, "deliveries": {}})


def _event_metadata(event):
    stamp = event.get("timestamp", 0)
    if not isinstance(stamp, (float, int)) or isinstance(stamp, bool):
        stamp = 0
    return {"latest_id": event["id"], "read_id": 0, "latest_at": stamp, "pending_ids": []}


def _pending_ids(data, chat_id, animal, sub, entry):
    """Known unread IDs survive inbox trimming; never mutate on a read path."""
    read_id, latest_id = entry.get("read_id", 0), entry.get("latest_id", 0)
    events = [event for event in data.get("web_bridge", {}).get("inboxes", {}).get(_scope(chat_id, animal), [])
              if event.get("role") == "assistant" and _positive_id(event.get("id"))
              and event.get("animal", animal) == animal and _consultation(animal, event) == sub]
    stored = entry.get("pending_ids")
    if isinstance(stored, list):
        ids = {identity for identity in stored if _positive_id(identity) and read_id < identity <= latest_id}
    else:
        # Migration cannot reconstruct already-discarded historical IDs. Preserve
        # the old latest-cursor reminder without moving its read baseline.
        ids = {event["id"] for event in events if read_id < event["id"] <= latest_id}
        if latest_id > read_id and not any(event["id"] == latest_id for event in events):
            ids.add(latest_id)
    if animal == "salchicher":
        ids.difference_update(event["id"] for event in events if retired_automatic_message(event))
        if sub == DEFAULT_SCOPE:
            # General clinic letters are deliberately transient. Removing or
            # expiring their content must not leave a persistent phantom badge.
            now = time.time()
            ids = {identity for identity in ids if _doctor_scope_exists(data, chat_id, sub, now, identity)}
    return sorted(ids)


def initialize(data):
    """Treat retained historical events as read once, without importing text."""
    if isinstance(data.get(STORE_KEY), dict) and data[STORE_KEY].get("version") == 1:
        changed = False
        for scope, records in data[STORE_KEY].get("scopes", {}).items():
            try:
                identity, animal = scope.split(":", 1)
                chat_id = int(identity)
            except (ValueError, TypeError):
                continue
            if not _positive_id(chat_id) or animal not in ANIMALS:
                continue
            for sub, entry in records.items():
                if not isinstance(entry.get("pending_ids"), list):
                    entry["pending_ids"] = _pending_ids(data, chat_id, animal, sub, entry)
                    changed = True
        return changed
    data[STORE_KEY] = {"version": 1, "scopes": {}, "deliveries": {}}
    state = data[STORE_KEY]
    for scope, events in data.get("web_bridge", {}).get("inboxes", {}).items():
        try:
            identity, animal = scope.split(":", 1)
            chat_id = int(identity)
        except (ValueError, TypeError):
            continue
        if not _positive_id(chat_id) or animal not in ANIMALS:
            continue
        for event in events:
            if event.get("role") != "assistant" or not _positive_id(event.get("id")):
                continue
            sub = _consultation(animal, event)
            records = state["scopes"].setdefault(_scope(chat_id, animal), {})
            if event["id"] > records.get(sub, {}).get("latest_id", 0):
                records[sub] = _event_metadata(event)
                records[sub]["read_id"] = event["id"]
    return True


def record(data, chat_id, animal, event):
    """Track a new assistant event; edits and duplicate IDs never reopen it."""
    if (not _positive_id(chat_id) or animal not in ANIMALS or not isinstance(event, dict)
            or event.get("role") != "assistant" or not _positive_id(event.get("id"))
            or event.get("animal", animal) != animal):
        return False
    # Production initializes before accepting traffic. A fresh standalone ledger
    # still records this supplied new event as unread rather than losing it.
    state = _state(data)
    records = state.setdefault("scopes", {}).setdefault(_scope(chat_id, animal), {})
    sub = _consultation(animal, event)
    previous = records.get(sub, {})
    if event["id"] <= previous.get("latest_id", 0):
        return False
    ids = _pending_ids(data, chat_id, animal, sub, previous)
    if not (animal == "salchicher" and retired_automatic_message(event)):
        ids.append(event["id"])
    records[sub] = {**_event_metadata(event), "read_id": previous.get("read_id", 0),
                    "pending_ids": ids}
    return True


def forget(data, chat_id, animal):
    """Forget one animal's read metadata, preserving other people and animals."""
    state = data.get(STORE_KEY, {})
    return state.get("scopes", {}).pop(_scope(chat_id, animal), None) is not None


def latest(data, chat_id, animal, consultation_id=None):
    """Cursor for a synchronous response containing this exact conversation."""
    sub = consultation_id if animal == "salchicher" and consultation_id else DEFAULT_SCOPE
    return data.get(STORE_KEY, {}).get("scopes", {}).get(_scope(chat_id, animal), {}).get(sub, {}).get("latest_id", 0)


def acknowledge(data, chat_id, animal, event_id, consultation_id=None):
    """Acknowledge an actual event in this scope, never a future/global cursor."""
    if (not _positive_id(chat_id) or animal not in ANIMALS or not _positive_id(event_id)
            or (consultation_id is not None and (animal != "salchicher"
                or not isinstance(consultation_id, str) or not consultation_id))):
        return False
    sub = consultation_id or DEFAULT_SCOPE
    entry = data.get(STORE_KEY, {}).get("scopes", {}).get(_scope(chat_id, animal), {}).get(sub)
    if not entry:
        return False
    # Persisted unread IDs also prove scope membership after the inbox is trimmed.
    ids = _pending_ids(data, chat_id, animal, sub, entry)
    known = event_id in ids or event_id in (entry.get("latest_id"), entry.get("read_id")) or any(
        event.get("id") == event_id and event.get("animal", animal) == animal
        and event.get("role") == "assistant"
        and _consultation(animal, event) == sub
        for event in data.get("web_bridge", {}).get("inboxes", {}).get(_scope(chat_id, animal), [])
    )
    if not known:
        return False
    entry["read_id"] = max(entry.get("read_id", 0), min(event_id, entry["latest_id"]))
    entry["pending_ids"] = [identity for identity in ids if identity > entry["read_id"]]
    return True


def _doctor_scope_exists(data, chat_id, sub, now, event_id=None):
    doctor = data.get("salchicher", {})
    session = doctor.get("sessions", {}).get(str(chat_id), {})
    if sub == DEFAULT_SCOPE:
        # General letters live in the clinic's transient feed, independently of
        # whether a consultation exists. Once that letter is erased/expired it
        # must not survive solely as unread metadata. Legacy consent-bound
        # messages in this same scope still require their original session.
        latest_id = event_id if event_id is not None else latest(data, chat_id, "salchicher")
        message = next((event for event in data.get("web_bridge", {}).get("inboxes", {})
                        .get(_scope(chat_id, "salchicher"), [])
                        if event.get("id") == latest_id and event.get("role") == "assistant"
                        and not event.get("consultation_id")), None)
        if message is None or message.get("timestamp", 0) <= now - 48 * 60 * 60:
            return False
        if not message.get("requires_consultation"):
            return True
        if session.get("consultation_id"):
            return False
    if sub != DEFAULT_SCOPE:
        retained = doctor.get("consultations", {}).get(str(chat_id), {}).get(sub)
        if retained and retained.get("retained") is True:
            return True
        if session.get("consultation_id") != sub:
            return False
    retention = 30 * 24 * 60 * 60 if session.get("retained") is True else 48 * 60 * 60
    return bool(session and session.get("updated_at", 0) > now - retention)


def _visible_doctor_unread_id(data, chat_id, sub, entry):
    """Ignore retired copy without acknowledging or rewriting any message.

    Keep the original cursor when its source has already been trimmed. If the
    latest source is a known retired template, an earlier visible unread event
    still deserves its reminder and can be acknowledged by its unchanged ID.
    """
    return max(_pending_ids(data, chat_id, "salchicher", sub, entry), default=0)


def pending(data, chat_id):
    """Return pending animal/episode identifiers; never conversation contents."""
    if not _positive_id(chat_id):
        return []
    result = []
    scopes = data.get(STORE_KEY, {}).get("scopes", {})
    now = time.time()
    for animal in sorted(ANIMALS):
        for sub, entry in scopes.get(_scope(chat_id, animal), {}).items():
            if entry.get("latest_id", 0) <= entry.get("read_id", 0):
                continue
            event_id = (_visible_doctor_unread_id(data, chat_id, sub, entry) if animal == "salchicher"
                        else max(_pending_ids(data, chat_id, animal, sub, entry), default=0))
            if not event_id:
                continue
            if animal == "salchicher":
                if not _doctor_scope_exists(data, chat_id, sub, now, event_id):
                    continue
            item = {"animal": animal, "event_id": event_id}
            if sub != DEFAULT_SCOPE:
                item["consultation_id"] = sub
            result.append(item)
    return result


def summary(data, chat_id):
    """Public unread metadata for one person's inbox, without message contents."""
    outstanding = {(item["animal"], item.get("consultation_id") or DEFAULT_SCOPE): item["event_id"]
                   for item in pending(data, chat_id)}
    stored = data.get(STORE_KEY, {}).get("scopes", {})
    animals = {}
    for animal in sorted(ANIMALS):
        scopes = []
        for sub, entry in stored.get(_scope(chat_id, animal), {}).items():
            read_id = entry.get("read_id", 0)
            latest_id = outstanding.get((animal, sub), entry.get("latest_id", 0))
            count = 0
            if (animal, sub) in outstanding:
                count = sum(identity <= latest_id for identity in _pending_ids(data, chat_id, animal, sub, entry))
            scopes.append({"consultation_id": None if sub == DEFAULT_SCOPE else sub,
                           "count": count, "latest_id": latest_id, "read_id": read_id})
        count = sum(item["count"] for item in scopes)
        general = next((item for item in scopes if item["consultation_id"] is None), {})
        animals[animal] = {"count": count, "has_new": count > 0, "scopes": scopes,
                           "latest_id": max((item["latest_id"] for item in scopes), default=0),
                           "read_id": general.get("read_id", 0)}
    return {"total_messages": sum(item["count"] for item in animals.values()),
            "total_chats": sum(item["has_new"] for item in animals.values()), "animals": animals}


class UnreadNotifier:
    """At most one generic notice per Madrid morning/evening slot and person."""

    def __init__(self, load, save, resolve_actor, get_bot, portal_url,
                 timezone=ZoneInfo("Europe/Madrid")):
        self.load, self.save = load, save
        self.resolve_actor, self.get_bot = resolve_actor, get_bot
        self.portal_url = portal_url
        self.timezone = ZoneInfo(timezone) if isinstance(timezone, str) else timezone
        self.lock = asyncio.Lock()

    def _save(self, data):
        try:
            self.save(data)
            return True
        except Exception as exc:
            logger.warning("Notification storage unavailable: %s", type(exc).__name__)
            return False

    async def tick(self, now=None):
        now = now or datetime.now(self.timezone)
        if now.tzinfo is None:
            raise ValueError("Notification time must have a timezone")
        local = now.astimezone(self.timezone)
        async with self.lock:
            data = copy.deepcopy(self.load())
            initialized = initialize(data)
            if local.hour not in (7, 19) or local.minute >= 15:
                if initialized:
                    self._save(data)
                return "skipped"
            try:
                chat_id = self.resolve_actor("sandra")
                owner_id = self.resolve_actor("owner")
                bot = self.get_bot()
                address = urlsplit(self.portal_url or "")
            except Exception:
                return "unavailable"
            if (not _positive_id(chat_id) or chat_id == owner_id or bot is None
                    or address.scheme != "https" or not address.hostname
                    or address.username or address.password):
                return "unavailable"
            state = _state(data)
            deliveries = state.setdefault("deliveries", {})
            slot = f"{chat_id}:{local.date().isoformat()}:{local.hour:02d}"
            if slot in deliveries:
                return "skipped"
            has_unread = bool(pending(data, chat_id))
            deliveries[slot] = {"status": "sending" if has_unread else "no_unread",
                                "at": local.isoformat()}
            # Two records/day; retain recent reservations across restarts without
            # retaining message content or accumulating unbounded state.
            for old_slot in list(deliveries)[:-64]:
                del deliveries[old_slot]
            if not self._save(data):
                return "unavailable"
            if not has_unread:
                return "no_unread"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                "Abrir Oficina Castori", url=self.portal_url)]])
            status = "sent"
            try:
                await bot.send_notification(chat_id=chat_id, text=NOTICE_TEXT, reply_markup=keyboard)
            except asyncio.CancelledError:
                # The persisted reservation prevents replay after shutdown even
                # when cancellation leaves Telegram's outcome unknown.
                raise
            except Exception as exc:
                status = "uncertain"
                logger.warning("Notification delivery uncertain: %s", type(exc).__name__)
            # Reload after awaiting: a reader or animal may have changed state.
            current = copy.deepcopy(self.load())
            receipt = current.get(STORE_KEY, {}).get("deliveries", {}).get(slot)
            if receipt is not None:
                receipt["status"] = status
                self._save(current)
            return status
