"""Read-only history/library views and an idempotent journal for future traffic.

Construct with (load_data, save_data, get_partner_chat_id, resolve_actor), then
await initialize() BEFORE starting any Telegram polling. The immutable JSON
baseline captures only history still present at cutover, without modifying its
source. Salchicher is never snapshotted or written to PostgreSQL.

The bridge owns history_outbox=[{animal,chat_id,event,epoch}] and durable
history_forgets={"chat:animal": {epoch,pending,...}}. Keep forget epochs forever
after marking pending=False. record_event()/forget() return False on unavailable
storage for retry; True also means an obsolete epoch was deliberately discarded.
"""

import asyncio
import base64
import copy
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import database
from salchicher_copy import retired_automatic_message


logger = logging.getLogger("control-castora.history")
ANIMALS = {"castori", "mimosuga", "vaca", "corte", "dulcimiel", "salchicher"}
BASELINE_KEY = "history_baseline"
RETENTION_SECONDS = 48 * 60 * 60
MAX_ID = 2**63 - 1


class HistoryUnavailable(RuntimeError):
    pass


def _date(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(value):
    parsed = _date(value)
    return parsed.isoformat() if parsed else None


def _scope(chat_id, animal):
    return f"{chat_id}:{animal}"


def _sort(message):
    stamp = _date(message.get("_sort_time", message.get("time")))
    return (1 if stamp else 0, stamp.timestamp() if stamp else 0, message["_sort_key"])


def _public(message):
    return {key: value for key, value in message.items() if not key.startswith("_")}


class HistoryService:
    def __init__(self, load, save, get_partner, resolve_actor, db=database):
        self.load, self.save = load, save
        self.get_partner, self.resolve_actor = get_partner, resolve_actor
        self.db = db
        self.locks = {}

    def _authorized(self, actor, chat_id):
        if (actor not in {"sandra", "owner"} or not isinstance(chat_id, int)
                or isinstance(chat_id, bool) or not 0 < chat_id <= MAX_ID
                or self.resolve_actor(actor) != chat_id):
            raise PermissionError("history_actor_not_allowed")

    def _eligible(self, chat_id):
        return isinstance(chat_id, int) and not isinstance(chat_id, bool) and 0 < chat_id <= MAX_ID and any(
            self.resolve_actor(actor) == chat_id for actor in ("sandra", "owner"))

    @staticmethod
    def _epoch(data, chat_id, animal):
        value = data.get("history_forgets", {}).get(_scope(chat_id, animal), {}).get("epoch", 0)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0

    def _proven_sandra(self, data, chat_id, animal):
        try:
            partner = self.get_partner(animal)
        except (KeyError, TypeError, ValueError):
            return False
        if self.resolve_actor("sandra") != chat_id or partner != chat_id:
            return False
        # An environment binding must not override conflicting identity evidence in
        # an unscoped legacy file. Unattributable history remains at its source.
        evidence = (data.get(f"{animal}_partner_chat_id"), data.get("starts", {}).get(animal))
        for value in evidence:
            if value is not None:
                try:
                    if int(value) != chat_id:
                        return False
                except (TypeError, ValueError):
                    return False
        return True

    @staticmethod
    def _legacy_messages(entries, chat_id, animal, label):
        result = []
        for index, item in enumerate(entries if isinstance(entries, list) else []):
            if not isinstance(item, dict):
                continue
            role = item.get("role") or {"in": "user", "out": "assistant"}.get(item.get("direction"))
            text = item.get("text", item.get("content"))
            if role not in {"user", "assistant"} or not isinstance(text, str) or not text:
                continue
            original_time = item.get("at", item.get("time"))
            digest = hashlib.sha256(json.dumps([chat_id, animal, label, index, item],
                                              sort_keys=True, default=str).encode()).hexdigest()[:24]
            result.append({"id": f"legacy:{digest}", "animal": animal, "role": role,
                           "text": text, "time": _iso(original_time), "source": label,
                           "_sort_key": f"legacy:{label}:{index:08}:{digest}"})
        return result

    @staticmethod
    def _event(event, animal):
        if not isinstance(event, dict):
            return None
        event_id = event.get("id")
        if (not isinstance(event_id, int) or isinstance(event_id, bool) or not 0 < event_id <= MAX_ID
                or event.get("role") not in {"user", "assistant"}
                or not isinstance(event.get("text"), str)):
            return None
        result = {"id": event_id, "event_id": event_id, "animal": animal, "role": event["role"],
                  "text": event["text"], "time": _iso(event.get("time")),
                  "source": event.get("source") if event.get("source") in {"web", "telegram"} else "telegram",
                  "_sort_key": f"event:{event_id:020}"}
        if isinstance(event.get("message_id"), int):
            result["message_id"] = event["message_id"]
        return result

    def _live_messages(self, data, chat_id, animal, epoch):
        events = data.get("web_bridge", {}).get("inboxes", {}).get(_scope(chat_id, animal), [])
        result = [entry for event in events if (entry := self._event(event, animal))]
        for queued in data.get("history_outbox", []):
            if (isinstance(queued, dict) and queued.get("chat_id") == chat_id
                    and queued.get("animal") == animal and queued.get("epoch", 0) == epoch):
                event = self._event(queued.get("event"), animal)
                if event:
                    result.append(event)
        return list({entry["id"]: entry for entry in result}.values())

    @staticmethod
    def _remove_known_overlap(messages, others):
        """Match exact text/role and original second one-to-one, never collapse repeats."""
        claimed = set()
        kept = []
        for message in reversed(messages):
            stamp = _date(message.get("time"))
            match = None
            if stamp:
                for index in range(len(others) - 1, -1, -1):
                    other = others[index]
                    other_time = _date(other.get("time"))
                    if (index not in claimed and other_time and int(stamp.timestamp()) == int(other_time.timestamp())
                            and message["role"] == other["role"] and message["text"] == other["text"]):
                        match = index
                        break
            if match is None:
                kept.append(message)
            else:
                claimed.add(match)
        return list(reversed(kept))

    @staticmethod
    def _merge_session_with_live(messages, live):
        """Replace undated session copies by the matching live events one-to-one.

        Work backwards through both ordered streams. Repeated identical messages
        remain separate occurrences; no synthetic timestamp or durable private copy
        is created to reconcile the original session's missing IDs and dates.
        """
        unmatched = []
        position = len(live) - 1
        for message in reversed(messages):
            match = next((index for index in range(position, -1, -1)
                          if live[index]["role"] == message["role"] and live[index]["text"] == message["text"]), None)
            if match is None:
                unmatched.append(message)
            else:
                position = match - 1
        return list(reversed(unmatched)) + live

    async def initialize(self):
        data = copy.deepcopy(self.load())
        if data.get(BASELINE_KEY, {}).get("version") == 1:
            return
        scopes = {}
        actors = [(actor, self.resolve_actor(actor)) for actor in ("sandra", "owner")]
        for actor, chat_id in actors:
            if not self._eligible(chat_id):
                continue
            for animal in sorted(ANIMALS - {"salchicher"}):
                if self._epoch(data, chat_id, animal) > 0:
                    continue
                legacy = []
                if actor == "sandra" and self._proven_sandra(data, chat_id, animal):
                    legacy = self._legacy_messages(data.get("history", {}).get(animal, []), chat_id, animal, "legacy")
                if animal == "vaca":
                    session = data.get("vaca", {}).get("sessions", {}).get(str(chat_id), {})
                    session_messages = self._legacy_messages(session.get("history", []), chat_id, animal, "session")
                    # Sessions have no message dates. Preserve their entries as unknown,
                    # rather than assigning the session's latest-update date to every turn.
                    legacy.extend(session_messages)
                live = self._live_messages(data, chat_id, animal, 0)
                if animal == "vaca":
                    # The original session is an ordered copy of recent turns, not
                    # another conversation. Prefer known dates/IDs where available.
                    dated = [message for message in legacy if message["source"] != "session"]
                    session_only = [message for message in legacy if message["source"] == "session"]
                    merged = self._merge_session_with_live(session_only, sorted(dated + live, key=_sort))
                    live_ids = {message["id"] for message in live}
                    legacy = [message for message in merged if message["id"] not in live_ids]
                legacy = self._remove_known_overlap(legacy, live)
                if legacy:
                    scopes[_scope(chat_id, animal)] = {"epoch": 0, "messages": legacy}
        data[BASELINE_KEY] = {"version": 1, "cutover": datetime.now(timezone.utc).isoformat(), "scopes": scopes}
        self.save(data)

    @staticmethod
    def _cursor(kind, chat_id, animal, epoch, message):
        value = {"v": 1, "kind": kind, "scope": _scope(chat_id, animal), "epoch": epoch,
                 "time": _iso(message.get("_sort_time", message.get("time"))), "key": message["_sort_key"]}
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")

    @staticmethod
    def _decode(before, kind, chat_id, animal, epoch):
        if before is None or before == "":
            return None
        try:
            if not isinstance(before, str) or len(before) > 512 or not all(c.isalnum() or c in "-_" for c in before):
                raise ValueError()
            value = json.loads(base64.urlsafe_b64decode(before + "=" * (-len(before) % 4)))
            if (not isinstance(value, dict) or set(value) != {"v", "kind", "scope", "epoch", "time", "key"}
                    or value["v"] != 1 or value["kind"] != kind or value["scope"] != _scope(chat_id, animal)
                    or value["epoch"] != epoch or not isinstance(value["key"], str) or len(value["key"]) > 160
                    or (value["time"] is not None and not _date(value["time"]))):
                raise ValueError()
            return value
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError):
            raise ValueError("invalid_cursor") from None

    @staticmethod
    def _limit(limit, maximum):
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= maximum:
            raise ValueError("invalid_limit")
        return limit

    async def page(self, actor, chat_id, animal, before=None, limit=40):
        self._authorized(actor, chat_id)
        if animal not in ANIMALS:
            raise ValueError("unknown_animal")
        limit = self._limit(limit, 100)
        data = self.load()
        epoch = self._epoch(data, chat_id, animal)
        cursor = self._decode(before, "history", chat_id, animal, epoch)
        baseline = data.get(BASELINE_KEY, {}).get("scopes", {}).get(_scope(chat_id, animal), {})
        if animal == "salchicher":
            return self._consultation_page(data, actor, chat_id, cursor, epoch, limit)
        local = copy.deepcopy(baseline.get("messages", [])) if baseline.get("epoch", 0) == epoch else []
        live = self._live_messages(data, chat_id, animal, epoch)
        local.extend(live)
        available = self.db.db_available()
        archived = []
        drafts = []
        if available:
            query_limit = limit + len(local) + 1
            try:
                rows = await self.db.get_conversation_archive(chat_id=chat_id, animal_key=animal, epoch=epoch,
                    before_time=_date(cursor["time"]) if cursor else None,
                    before_key=cursor["key"] if cursor else None, limit=query_limit)
                for row in rows:
                    event_id = row.get("event_id")
                    archived.append({"id": event_id if event_id else f"archive:{row['id']}",
                        "event_id": event_id, "animal": animal, "role": row["role"], "text": row["text"],
                        "time": _iso(row.get("occurred_at")), "source": row["source"],
                        "_sort_key": row["source_key"],
                        **({"message_id": row["message_id"]} if row.get("message_id") is not None else {})})
                cutover = _date(data.get(BASELINE_KEY, {}).get("cutover"))
                if animal == "mimosuga" and cutover and epoch == 0:
                    draft_rows = await self.db.get_sent_auto_reply_archive(chat_id=chat_id, cutover=cutover,
                        before_time=_date(cursor["time"]) if cursor else None,
                        before_key=cursor["key"] if cursor else None, limit=query_limit,
                        known_messages=[{"identity": f"event:{message['id']}" if isinstance(message["id"], int) else str(message["id"]),
                                         "role": message["role"], "text": message["text"], "time": message.get("time")}
                                        for message in {message["id"]: message for message in local}.values()])
                    for row in draft_rows:
                        drafts.append({"id": row["source_key"], "animal": animal, "role": row["role"],
                            "text": row["text"], "time": _iso(row.get("occurred_at")), "source": "telegram_archive",
                            "recorded_at": _iso(row.get("recorded_at")), "_sort_time": _iso(row["sort_at"]),
                            "_sort_key": row["source_key"], "_overlap_rank": row.get("overlap_rank"),
                            **({"grouped_input": True} if row["role"] == "user" else {})})
            except Exception as exc:
                logger.warning("History archive read failed: %s", type(exc).__name__)
                raise HistoryUnavailable("history_unavailable") from None
        known = list({message["id"]: message for message in local + archived}.values())
        # A forget can happen while PostgreSQL is awaited. Never return a stale
        # epoch that could repopulate a browser immediately after erasure.
        if self._epoch(self.load(), chat_id, animal) != epoch:
            raise ValueError("history_epoch_changed")
        return self._page_result(known + drafts, cursor, limit, actor, chat_id, animal, epoch, available)

    def _consultation_page(self, data, actor, chat_id, cursor, epoch, limit):
        session = data.get("salchicher", {}).get("sessions", {}).get(str(chat_id), {})
        if not session or session.get("updated_at", 0) <= time.time() - RETENTION_SECONDS:
            messages = []
        else:
            messages = self._legacy_messages(session.get("history", []), chat_id, "salchicher", "active_session")
            live = self._live_messages(data, chat_id, "salchicher", epoch)
            live = [message for message in live if (stamp := _date(message.get("time")))
                    and stamp.timestamp() > time.time() - RETENTION_SECONDS]
            messages = self._merge_session_with_live(messages, sorted(live, key=_sort))
        messages = [message for message in messages if not retired_automatic_message(message)]
        return self._page_result(messages, cursor, limit, actor, chat_id, "salchicher", epoch, False,
                                 retention="active_consultation_48h")

    def _page_result(self, messages, cursor, limit, actor, chat_id, animal, epoch, available, **extra):
        unique = list({message["id"]: message for message in messages}.values())
        if cursor:
            marker = {"time": cursor["time"], "_sort_key": cursor["key"]}
            unique = [message for message in unique if _sort(message) < _sort(marker)]
        ordered = sorted(unique, key=_sort, reverse=True)
        selected = ordered[:limit]
        more = len(ordered) > limit
        next_cursor = self._cursor("history", chat_id, animal, epoch, selected[-1]) if more and selected else None
        return {"messages": [_public(message) for message in reversed(selected)],
                "next_cursor": next_cursor, "has_more": more, "archive_available": available, **extra}

    async def record_event(self, animal, chat_id, event, *, epoch=0):
        if animal == "salchicher":
            return True
        if animal not in ANIMALS or not self._eligible(chat_id):
            return True
        message = self._event(event, animal)
        if not message:
            return True
        async with self.locks.setdefault(_scope(chat_id, animal), asyncio.Lock()):
            if epoch != self._epoch(self.load(), chat_id, animal):
                return True
            if not self.db.db_available():
                return False
            try:
                await self.db.archive_conversation_event(chat_id=chat_id, animal_key=animal,
                    source_key=message["_sort_key"], event_id=message["id"], source=message["source"],
                    role=message["role"], text=message["text"], occurred_at=_date(message["time"]),
                    epoch=epoch, message_id=message.get("message_id"))
                return True
            except Exception as exc:
                logger.warning("History archive write deferred: %s", type(exc).__name__)
                return False

    async def forget(self, animal, chat_id, *, epoch):
        if animal not in {"vaca", "salchicher"} or not self._eligible(chat_id):
            return True
        async with self.locks.setdefault(_scope(chat_id, animal), asyncio.Lock()):
            data = copy.deepcopy(self.load())
            if epoch != self._epoch(data, chat_id, animal):
                return True
            data.get(BASELINE_KEY, {}).get("scopes", {}).pop(_scope(chat_id, animal), None)
            self.save(data)
            if animal == "salchicher":
                return True
            if not self.db.db_available():
                return False
            try:
                await self.db.delete_conversation_archive_before_epoch(chat_id=chat_id, animal_key=animal, epoch=epoch)
                return True
            except Exception as exc:
                logger.warning("History archive erasure deferred: %s", type(exc).__name__)
                return False

    async def stories(self, actor, chat_id, before=None, limit=12):
        self._authorized(actor, chat_id)
        limit = self._limit(limit, 50)
        cursor = self._decode(before, "stories", chat_id, "mimosuga", 0)
        if not self.db.db_available():
            raise HistoryUnavailable("story_archive_unavailable")
        try:
            before_id = int(cursor["key"]) if cursor else None
            if cursor and (cursor["time"] is None or not 0 < before_id <= MAX_ID):
                raise ValueError("invalid_cursor")
        except (TypeError, ValueError):
            raise ValueError("invalid_cursor") from None
        try:
            rows = await self.db.get_delivered_stories(chat_id=chat_id,
                before_time=_date(cursor["time"]) if cursor else None, before_id=before_id, limit=limit + 1)
        except Exception as exc:
            logger.warning("Story library read failed: %s", type(exc).__name__)
            raise HistoryUnavailable("story_archive_unavailable") from None
        selected = rows[:limit]
        more = len(rows) > limit
        next_cursor = None
        if more and selected:
            last = selected[-1]
            next_cursor = self._cursor("stories", chat_id, "mimosuga", 0,
                                      {"time": last["delivered_at"], "_sort_key": str(last["id"])})
        return {"stories": [self._story_public(row) for row in selected], "next_cursor": next_cursor,
                "has_more": more, "archive_available": True}

    @staticmethod
    def _story_public(row):
        return {"id": row["id"], "title": row["title"], "created_at": _iso(row["created_at"]),
                "delivered_at": _iso(row["delivered_at"]), "excerpt": row.get("summary", ""),
                "narrator": row["narrator"]}

    async def story(self, actor, chat_id, story_id):
        self._authorized(actor, chat_id)
        if not isinstance(story_id, int) or isinstance(story_id, bool) or not 0 < story_id <= MAX_ID:
            raise ValueError("invalid_story_id")
        if not self.db.db_available():
            raise HistoryUnavailable("story_archive_unavailable")
        try:
            row = await self.db.get_delivered_story(chat_id=chat_id, story_id=story_id)
        except Exception as exc:
            logger.warning("Story detail read failed: %s", type(exc).__name__)
            raise HistoryUnavailable("story_archive_unavailable") from None
        return {"story": {**self._story_public(row), "text": row["full_text"]}} if row else None
