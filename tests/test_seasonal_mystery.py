"""Server clock and authenticated HTTP tests; no real accounts or services."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer

import seasonal_mystery
from portal import COOKIE
from web_bridge import WebBridge


DAYS = (1, 4, 7, 10, 13, 16, 19)
TOKEN = "fictional-mystery-server-token-more-than-32-characters"
ORIGIN = "https://house.example"
INTERNAL = {"Authorization": "Bearer " + TOKEN, "X-Castori-Actor": "sandra"}


def fixture():
    return {
        "id": "seven-seals-2026",
        "finale_at": "2026-11-22T00:00:00+01:00",
        "expires_at": "2027-01-11T00:00:00+01:00",
        "brand": "PRIVATE_BRAND",
        "solution": "PRIVATE_FINAL_SOLUTION",
        "entries": [
            {"id": f"{index:02d}", "release_at": f"2026-11-{day:02d}T00:00:00+01:00",
             "title": f"TITLE_{index}", "lines": [f"RIDDLE_{index}", f"SECOND_LINE_{index}"],
             "hint": f"HINT_{index}", "solution": f"PRIVATE_ANSWER_{index}", "brand": "PRIVATE_BRAND"}
            for index, day in enumerate(DAYS, 1)
        ],
    }


def at(value):
    return datetime.fromisoformat(value)


class MysteryCalendarTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "seasonal_mystery.json"
        self.calendar = fixture()
        self.path.write_text(json.dumps(self.calendar), encoding="utf-8")
        self.patch = patch.object(seasonal_mystery, "DATA_PATH", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_each_madrid_midnight_releases_exactly_one_seal_and_never_future_content(self):
        for count, entry in enumerate(self.calendar["entries"], 1):
            release = at(entry["release_at"])
            for offset, expected in ((-1, count - 1), (0, count), (1, count)):
                with self.subTest(day=release.day, offset=offset):
                    snapshot = seasonal_mystery.public_snapshot(release + timedelta(microseconds=offset))
                    self.assertEqual([item["id"] for item in snapshot["entries"]], [f"{i:02d}" for i in range(1, expected + 1)])
                    self.assertEqual(snapshot["total"], 7)
                    self.assertEqual(snapshot["next_unlock_at"], self.calendar["entries"][expected]["release_at"] if expected < 7 else None)
                    encoded = json.dumps(snapshot)
                    for index in range(expected + 1, 8):
                        for prefix in ("TITLE_", "RIDDLE_", "SECOND_LINE_", "HINT_"):
                            self.assertNotIn(prefix + str(index), encoded)
                    self.assertNotIn("PRIVATE_", encoded)

    def test_snapshot_whitelists_every_field_without_answers_or_private_metadata(self):
        snapshot = seasonal_mystery.public_snapshot(at(self.calendar["finale_at"]))
        self.assertEqual(set(snapshot), {"id", "server_now", "finale_at", "next_unlock_at", "total", "closed", "visible", "entries"})
        for entry in snapshot["entries"]:
            self.assertEqual(set(entry), {"id", "release_at", "title", "lines", "hint"})
        self.assertNotIn("PRIVATE_", json.dumps(snapshot))

    def test_finale_and_expiry_use_exact_instants_including_last_day(self):
        finale, expiry = at(self.calendar["finale_at"]), at(self.calendar["expires_at"])
        self.assertFalse(seasonal_mystery.public_snapshot(finale - timedelta(microseconds=1))["closed"])
        self.assertTrue(seasonal_mystery.public_snapshot(finale)["closed"])
        self.assertTrue(seasonal_mystery.public_snapshot(expiry - timedelta(microseconds=1))["visible"])
        self.assertFalse(seasonal_mystery.public_snapshot(expiry)["visible"])
        self.assertEqual(seasonal_mystery.public_snapshot(finale)["next_unlock_at"], None)

    def test_clock_is_server_utc_by_default_and_equivalent_offsets_match(self):
        instant = at("2026-11-03T23:00:00+00:00")
        snapshot = seasonal_mystery.public_snapshot(instant)
        self.assertEqual(snapshot["server_now"], instant.isoformat())
        self.assertEqual(snapshot, seasonal_mystery.public_snapshot(at("2026-11-04T00:00:00+01:00")))
        before = datetime.now(timezone.utc)
        snapshot = seasonal_mystery.public_snapshot()
        after = datetime.now(timezone.utc)
        self.assertLessEqual(before, at(snapshot["server_now"]))
        self.assertLessEqual(at(snapshot["server_now"]), after)
        with self.assertRaises(ValueError):
            seasonal_mystery.public_snapshot(datetime(2026, 11, 22))

    def test_invalid_source_fails_closed_and_source_is_not_mutated(self):
        contents = self.path.read_bytes()
        seasonal_mystery.public_snapshot(at("2026-11-01T00:00:00+01:00"))
        self.assertEqual(self.path.read_bytes(), contents)
        self.calendar["entries"][0]["release_at"] = "2026-11-01T00:00:00"
        self.path.write_text(json.dumps(self.calendar), encoding="utf-8")
        with self.assertRaises(ValueError):
            seasonal_mystery.public_snapshot()


class MysteryHttpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.source = root / "seasonal_mystery.json"
        self.source.write_text(json.dumps(fixture()), encoding="utf-8")
        self.source_patch = patch.object(seasonal_mystery, "DATA_PATH", self.source)
        self.source_patch.start()
        portal_root = root / "portal_web"
        portal_root.mkdir()
        self.accounts = AsyncMock()
        self.accounts.get_session.side_effect = lambda token: {
            "sandra-session": {"actor": "sandra", "chat_id": 11, "username": "patita"},
            "owner-session": {"actor": "owner", "chat_id": 22, "username": "castor"},
        }.get(token)
        self.load, self.save = Mock(return_value={}), Mock()
        self.bridge = WebBridge(self.load, self.save, lambda: {}, lambda role: {"sandra": 11, "owner": 22}.get(role),
                                token=TOKEN, account_service=self.accounts, portal_origin=ORIGIN, portal_root=portal_root)
        self.client = TestClient(TestServer(self.bridge.create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.bridge.close()
        self.source_patch.stop()
        self.directory.cleanup()

    async def test_both_authenticated_transports_return_the_same_filtered_read_only_snapshot(self):
        expected = seasonal_mystery.public_snapshot(at("2026-11-04T00:00:00+01:00"))
        with patch.object(seasonal_mystery, "public_snapshot", return_value=expected) as provider:
            for actor in ("sandra", "owner"):
                for path, headers in (
                    ("/castori-web/seasonal-mystery", {**INTERNAL, "X-Castori-Actor": actor}),
                    ("/api/bridge/seasonal-mystery", {"Cookie": f"{COOKIE}={actor}-session"}),
                ):
                    response = await self.client.get(path, headers=headers)
                    self.assertEqual(response.status, 200)
                    self.assertEqual(await response.json(), expected)
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertEqual(provider.call_count, 4)
            for call in provider.call_args_list:
                self.assertEqual(call.args, ())
                self.assertEqual(call.kwargs, {})
        self.load.assert_not_called()
        self.save.assert_not_called()

    async def test_anonymous_invalid_and_forged_identities_cannot_read(self):
        cases = (
            ("/castori-web/seasonal-mystery", {}, 401),
            ("/castori-web/seasonal-mystery", {**INTERNAL, "X-Castori-Actor": "visitor"}, 403),
            ("/api/bridge/seasonal-mystery", {}, 401),
            ("/api/bridge/seasonal-mystery", INTERNAL, 401),
            ("/api/bridge/seasonal-mystery", {"Cookie": f"{COOKIE}=invalid"}, 401),
            ("/api/bridge/seasonal-mystery", {"Cookie": f"{COOKIE}=sandra-session; {COOKIE}=owner-session"}, 401),
        )
        with patch.object(seasonal_mystery, "public_snapshot") as provider:
            for path, headers, status in cases:
                response = await self.client.get(path, headers=headers)
                self.assertEqual(response.status, status)
            provider.assert_not_called()

    async def test_queries_cannot_override_server_clock_or_request_locked_seals(self):
        with patch.object(seasonal_mystery, "public_snapshot") as provider:
            for prefix, headers in (("/castori-web/", INTERNAL), ("/api/bridge/", {"Cookie": f"{COOKIE}=sandra-session"})):
                for query in ("now=2099-01-01", "date=2099-01-01", "preview=1", "id=07", "actor=owner", "day=19", "unlock=all", "id=01&id=07"):
                    response = await self.client.get(prefix + "seasonal-mystery?" + query, headers=headers)
                    self.assertEqual(response.status, 400)
                    self.assertEqual(await response.json(), {"error": "invalid_query"})
            provider.assert_not_called()

    async def test_endpoint_is_get_only_and_calendar_file_is_not_a_public_asset(self):
        for prefix, headers in (("/castori-web/", INTERNAL), ("/api/bridge/", {"Cookie": f"{COOKIE}=sandra-session", "Origin": ORIGIN})):
            response = await self.client.post(prefix + "seasonal-mystery", json={}, headers=headers)
            self.assertEqual(response.status, 405)
        for path in ("/castori/seasonal_mystery.json", "/seasonal_mystery.json"):
            response = await self.client.get(path)
            self.assertNotEqual(response.status, 200)
            self.assertNotIn("RIDDLE_", await response.text())
        self.save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
