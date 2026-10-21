"""Read-only, allowlisted state for Miguel's private Centralita panel.

The HTTP bridge must authenticate the owner before invoking this provider. This
class never dispatches commands, writes state, sends Telegram messages or exposes
raw bot data. In particular, Salchicher contributes only its global enabled flag.
Pass the callable instance as WebBridge's ``admin_state_provider``. Callbacks
resolve the live main.py runtime without importing main or creating a cycle.
"""

import asyncio
from datetime import datetime, timezone as utc_timezone
from typing import Any, Callable

import database


ANIMALS = {
    "castori": "Oficina Castori",
    "mimosuga": "Mimosuga",
    "corte": "Corte de Pompones y Plumas",
    "salchicher": "Doctor Salchicher",
    "vaca": "Vaca Mágica",
}
COUNT_FIELDS = (
    "stories_total", "stories_pending", "stories_canon", "active_story_offers",
    "auto_reply_pending", "auto_reply_sent", "court_cases_active",
)
VISIT_EVENTS = ("pista1", "pista2", "manana")


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: Any, limit: int = 16000) -> str:
    return value[:limit] if isinstance(value, str) else ""


def _date(value: Any) -> str | None:
    """Preserve real timestamps; unknown dates stay unknown."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return None


def _positive_id(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


class AdminService:
    def __init__(self, load_data: Callable, get_apps: Callable,
                 get_partner_chat_id: Callable, owner_chat_id: Callable,
                 admin_chat_id: Callable, *, get_admin_app: Callable,
                 next_schedule_time: Callable, timezone=utc_timezone.utc,
                 get_vaca_partner: Callable | None = None, db=database,
                 limit: int = 20):
        self.load = load_data
        self.get_apps = get_apps
        self.get_partner = get_partner_chat_id
        self.owner_id = owner_chat_id
        self.admin_id = admin_chat_id
        self.get_admin_app = get_admin_app
        self.next_schedule = next_schedule_time
        self.timezone = timezone
        self.get_vaca_partner = get_vaca_partner or (lambda: self.get_partner("vaca"))
        self.db = db
        self.limit = max(1, min(int(limit), 20))

    async def __call__(self) -> dict[str, Any]:
        data = _mapping(self.load())
        apps = self.get_apps()
        now = datetime.now(self.timezone)
        partners = {key: self.get_partner(key) for key in ANIMALS}
        identity_matches = self.owner_id() == self.admin_id()
        mimosuga = _mapping(_mapping(data.get("auto_replies")).get("mimosuga"))
        mode = mimosuga.get("mode", "review")
        campaigns = _mapping(data.get("vaca_campaigns"))
        result = {
            "available": self.get_admin_app() is not None,
            "database_available": bool(self.db.db_available()),
            "admin_identity_matches": identity_matches,
            "timezone": str(self.timezone),
            "animals": [{"id": key, "name": name, "available": key in apps,
                         "linked": bool(partners[key])} for key, name in ANIMALS.items()],
            "automation": {
                "schedules_paused": bool(data.get("schedules_paused", False)),
                "mimosuga_enabled": bool(mimosuga.get("enabled", False)),
                "mimosuga_mode": mode if mode in {"review", "auto"} else "review",
                "salchicher_enabled": bool(_mapping(data.get("salchicher")).get("enabled", True)),
                "vaca_enabled": bool(_mapping(data.get("vaca")).get("enabled", True)),
                "vaca_visits_paused": bool(campaigns.get("paused", False)),
            },
            "counts": {}, "schedules": [], "stories": [], "drafts": [],
            "visits": [], "wishes": [], "court": None,
            "truncated": {}, "errors": [],
        }

        schedules = []
        for item in data.get("schedules", []) if isinstance(data.get("schedules", []), list) else []:
            if not isinstance(item, dict) or item.get("animal_key") not in ANIMALS:
                continue
            try:
                upcoming = self.next_schedule(item, now)
            except (KeyError, ValueError, TypeError, OverflowError):
                upcoming = None
            schedule = {
                "id": _text(item.get("id"), 80), "animal": item["animal_key"],
                "text": _text(item.get("text")), "kind": item.get("kind", "weekly"),
                "time": _text(item.get("time"), 5), "next_at": _date(upcoming),
                "sent": bool(item.get("sent", False)), "sending": bool(item.get("sending", False)),
            }
            if schedule["kind"] == "weekly":
                day = item.get("weekday")
                schedule["day"] = day if isinstance(day, int) and 0 <= day <= 6 else None
            else:
                schedule["date"] = _text(item.get("date"), 10)
            schedules.append(schedule)
        schedules.sort(key=lambda row: (row["next_at"] is None, row["next_at"] or "", row["id"]))
        result["counts"]["schedules_active"] = sum(row["kind"] == "weekly" or not row["sent"] for row in schedules)
        result["schedules"] = schedules[:self.limit]
        result["truncated"]["schedules"] = len(schedules) > self.limit

        visits = []
        for key, raw in _mapping(campaigns.get("plans")).items():
            if not isinstance(raw, dict):
                continue
            events = _mapping(raw.get("events"))
            visits.append({
                "id": _text(raw.get("id", key), 80), "status": _text(raw.get("status"), 30),
                "gifts": _text(raw.get("gifts"), 2000), "delivery_at": _date(raw.get("delivery_at")),
                "created_at": _date(raw.get("created_at")),
                "events": [{"id": event, "at": _date(_mapping(events.get(event)).get("at")),
                            "text": _text(_mapping(events.get(event)).get("text"), 3500),
                            "status": _text(_mapping(events.get(event)).get("status"), 30)}
                           for event in VISIT_EVENTS if event in events],
            })
        visits.sort(key=lambda row: (row["created_at"] or "", row["id"]), reverse=True)
        result["counts"]["visits_active"] = sum(row["status"] == "active" for row in visits)
        result["visits"] = visits[:self.limit]
        result["truncated"]["visits"] = len(visits) > self.limit

        # Miguel sees Patita's gift notebook, never his own test notebook or her conversation.
        vaca_partner = self.get_vaca_partner()
        sessions = _mapping(_mapping(data.get("vaca")).get("sessions"))
        wishes = _mapping(sessions.get(str(vaca_partner))).get("wishes", []) if vaca_partner else []
        wishes = [wish for wish in wishes if isinstance(wish, dict)] if isinstance(wishes, list) else []
        result["wishes"] = [{"id": _text(wish.get("id"), 40), "name": _text(wish.get("name"), 240),
                             "details": _text(wish.get("details"), 2000), "url": _text(wish.get("url"), 1200),
                             "favorite": bool(wish.get("favorite", False))} for wish in wishes[:60]]
        result["truncated"]["wishes"] = len(wishes) > 60
        if not result["database_available"]:
            result["errors"].append("database_unavailable")
            return result

        queries = [("counts", self.db.get_system_status_counts())]
        if identity_matches:
            queries.append(("stories", self.db.get_latest_stories(self.limit + 1)))
        if partners["mimosuga"]:
            queries.append(("drafts", self.db.get_pending_auto_reply_drafts(
                animal_key="mimosuga", chat_id=partners["mimosuga"], limit=self.limit + 1)))
        if partners["corte"]:
            queries.append(("court", self.db.get_latest_court_case(partners["corte"])))
        values = await asyncio.gather(*(query for _, query in queries), return_exceptions=True)
        for (name, _), value in zip(queries, values):
            if isinstance(value, BaseException):
                result["errors"].append(f"{name}_unavailable")
                continue
            if name == "counts":
                result["counts"].update({key: max(0, int(value[key])) for key in COUNT_FIELDS
                                          if isinstance(_mapping(value).get(key), int)})
            elif name == "stories":
                rows = [row for row in value if isinstance(row, dict) and _positive_id(row.get("id"))]
                result["stories"] = [{"id": row["id"], "title": _text(row.get("title"), 500),
                                       "status": _text(row.get("status"), 30),
                                       "narrator": _text(row.get("narrator"), 100),
                                       "created_at": _date(row.get("created_at"))} for row in rows[:self.limit]]
                result["truncated"]["stories"] = len(rows) > self.limit
            elif name == "drafts":
                # Check scope again at the projection boundary even with the SQL predicate.
                rows = [row for row in value if isinstance(row, dict) and _positive_id(row.get("id"))
                        and row.get("status") == "pending" and row.get("animal_key") == "mimosuga"
                        and row.get("incoming_chat_id") == partners["mimosuga"]]
                result["drafts"] = [{"id": row["id"], "animal": row["animal_key"],
                                     "incoming_text": _text(row.get("incoming_text")),
                                     "proposed_text": _text(row.get("proposed_text")), "status": "pending",
                                     "created_at": _date(row.get("created_at"))} for row in rows[:self.limit]]
                result["truncated"]["drafts"] = len(rows) > self.limit
            elif name == "court" and isinstance(value, dict):
                result["court"] = {"id": _positive_id(value.get("id")),
                                   **{key: _text(value.get(key)) for key in
                                      ("status", "accuser", "accusation", "verdict", "sentence_text")}}
        return result
