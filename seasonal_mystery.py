"""Release the seven seals from a server-only calendar, using server time."""

import json
from datetime import datetime, timezone
from pathlib import Path


DATA_PATH = Path(__file__).with_name("seasonal_mystery.json")
PUBLIC_ENTRY_FIELDS = ("id", "release_at", "title", "lines", "hint")


def _instant(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("Mystery dates must include a timezone")
    return result.astimezone(timezone.utc)


def _calendar():
    # This file stays beside the Python source, never in portal_web or web/.
    campaign = json.loads(DATA_PATH.read_text(encoding="utf-8-sig"))
    if not isinstance(campaign, dict) or not isinstance(campaign.get("id"), str):
        raise ValueError("Invalid mystery calendar")
    finale, expires = _instant(campaign["finale_at"]), _instant(campaign["expires_at"])
    entries = campaign.get("entries")
    if finale >= expires or not isinstance(entries, list) or len(entries) != 7:
        raise ValueError("Invalid mystery schedule")
    scheduled, seen = [], set()
    for entry in entries:
        if (not isinstance(entry, dict)
                or any(not isinstance(entry.get(key), str) for key in ("id", "release_at", "title", "hint"))
                or not isinstance(entry.get("lines"), list)
                or any(not isinstance(line, str) for line in entry["lines"])
                or entry["id"] in seen):
            raise ValueError("Invalid mystery entry")
        release = _instant(entry["release_at"])
        if release >= finale:
            raise ValueError("Mystery entries must precede the finale")
        seen.add(entry["id"])
        scheduled.append((release, entry))
    scheduled.sort(key=lambda item: item[0])
    return campaign, finale, expires, scheduled


def public_snapshot(now: datetime | None = None) -> dict:
    """Return only unlocked text; no client input can select the clock or a seal."""
    instant = datetime.now(timezone.utc) if now is None else now
    if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Mystery clock must be a timezone-aware datetime")
    instant = instant.astimezone(timezone.utc)
    campaign, finale, expires, scheduled = _calendar()
    unlocked = []
    for release, entry in scheduled:
        if release <= instant:
            # Project fields explicitly. Answers and private metadata never travel.
            public = {key: entry[key] for key in PUBLIC_ENTRY_FIELDS}
            public["lines"] = list(entry["lines"])
            unlocked.append(public)
    next_unlock = next((entry["release_at"] for release, entry in scheduled if release > instant), None)
    return {
        "id": campaign["id"],
        "server_now": instant.isoformat(),
        "finale_at": campaign["finale_at"],
        "next_unlock_at": next_unlock,
        "total": len(scheduled),
        "closed": instant >= finale,
        "visible": instant < expires,
        "entries": unlocked,
    }
