import copy
import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import database
from admin_service import AdminService


NOW = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class AdminServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = {
            "TOKEN_CENTRALITA": "TOKEN_SENTINEL", "secret": "RAW_STATE_SENTINEL",
            "salchicher": {"enabled": False, "sessions": {"11": {
                "shared": False, "history": [{"content": "PRIVATE_MEDICAL_SENTINEL"}]}}},
            "auto_replies": {"mimosuga": {"enabled": True, "mode": "auto"}},
            "schedules_paused": True,
            "schedules": [{"id": "s1", "animal_key": "castori", "kind": "weekly",
                           "weekday": 3, "time": "19:00", "text": "Una carta bonita", "secret": "RAW_SCHEDULE"}],
            "vaca": {"enabled": True, "sessions": {
                "11": {"history": [{"text": "PRIVATE_VACA_CHAT"}], "wishes": [
                    {"id": "w1", "name": "Patita wishlist", "details": "Suave", "url": "",
                     "favorite": True, "secret": "RAW_WISH"}]},
                "22": {"wishes": [{"id": "w2", "name": "OWNER_TEST_WISHLIST"}]},
            }},
            "vaca_campaigns": {"paused": True, "plans": {"v1": {
                "id": "v1", "status": "draft", "gifts": "SECRET_GIFT_FOR_MIGUEL",
                "created_at": NOW.isoformat(), "delivery_at": "2026-12-25T08:00:00+01:00",
                "recipient_id": 11, "secret": "RAW_VISIT",
                "events": {"pista1": {"at": "2026-12-22T18:00:00+01:00", "text": "Una pista",
                                      "status": "pending", "attempt_id": "RAW_ATTEMPT"}}}}},
        }
        self.partners = {key: 11 for key in ("castori", "mimosuga", "corte", "salchicher", "vaca")}
        self.db = SimpleNamespace(
            db_available=lambda: True,
            get_system_status_counts=AsyncMock(return_value={"stories_total": 30, "auto_reply_pending": 1,
                                                           "secret": "SQL_SECRET"}),
            get_latest_stories=AsyncMock(return_value=[{"id": 1, "title": "La mantita", "status": "pending",
                "narrator": "Mimosuga", "created_at": NOW, "full_text": "FULL_STORY_NOT_IN_PANEL"}]),
            get_pending_auto_reply_drafts=AsyncMock(return_value=[{"id": 7, "animal_key": "mimosuga",
                "incoming_chat_id": 11, "incoming_text": "Hola", "proposed_text": "Hola, patita",
                "status": "pending", "created_at": NOW, "admin_user_id": 22, "reason": "RAW_REASON"}]),
            get_latest_court_case=AsyncMock(return_value={"id": 5, "status": "active", "accuser": "admin",
                "accusation": "Hurto de mantita", "chat_id": 11, "secret": "COURT_SECRET"}),
        )
        self.service = AdminService(lambda: self.data, lambda: {"castori": object(), "vaca": object()},
            self.partners.get, lambda: 22, lambda: 22, get_admin_app=lambda: object(),
            next_schedule_time=lambda schedule, now: NOW, timezone=timezone.utc,
            get_vaca_partner=lambda: 11, db=self.db)

    async def test_projection_is_read_only_and_excludes_sessions_credentials_and_raw_state(self):
        previous = copy.deepcopy(self.data)
        result = await self.service()
        payload = json.dumps(result)
        for sentinel in ("TOKEN_SENTINEL", "RAW_STATE_SENTINEL", "PRIVATE_MEDICAL_SENTINEL",
                         "PRIVATE_VACA_CHAT", "OWNER_TEST_WISHLIST", "RAW_SCHEDULE", "RAW_WISH",
                         "RAW_VISIT", "RAW_ATTEMPT", "SQL_SECRET", "RAW_REASON", "COURT_SECRET",
                         "FULL_STORY_NOT_IN_PANEL", "incoming_chat_id", "recipient_id", "admin_user_id"):
            self.assertNotIn(sentinel, payload)
        self.assertEqual(self.data, previous)
        self.assertEqual(result["wishes"][0]["name"], "Patita wishlist")
        self.assertEqual(result["visits"][0]["gifts"], "SECRET_GIFT_FOR_MIGUEL")
        self.assertEqual(result["visits"][0]["events"][0], {
            "id": "pista1", "at": "2026-12-22T18:00:00+01:00", "text": "Una pista", "status": "pending"})
        self.assertEqual(result["court"]["accusation"], "Hurto de mantita")
        self.assertTrue(result["available"])
        self.assertEqual(result["errors"], [])

    async def test_automation_and_availability_match_native_settings(self):
        result = await self.service()
        self.assertEqual(result["automation"], {"schedules_paused": True, "mimosuga_enabled": True,
            "mimosuga_mode": "auto", "salchicher_enabled": False, "vaca_enabled": True, "vaca_visits_paused": True})
        animals = {animal["id"]: animal for animal in result["animals"]}
        self.assertTrue(animals["castori"]["available"])
        self.assertFalse(animals["mimosuga"]["available"])
        self.assertNotIn("dulcimiel", animals)
        self.assertEqual(result["stories"][0]["created_at"], NOW.isoformat())
        self.data["auto_replies"]["mimosuga"]["mode"] = "invalid"
        self.assertEqual((await self.service())["automation"]["mimosuga_mode"], "review")

    async def test_database_outage_preserves_local_state_without_fabricating_sql_counts(self):
        self.db.db_available = lambda: False
        result = await self.service()
        self.assertFalse(result["database_available"])
        self.assertEqual(result["errors"], ["database_unavailable"])
        self.assertNotIn("stories_total", result["counts"])
        self.assertEqual(result["stories"], [])
        self.assertEqual(len(result["schedules"]), 1)
        self.db.get_system_status_counts.assert_not_awaited()

    async def test_independent_query_failure_is_explicit_and_does_not_leak_exception(self):
        self.db.get_latest_stories.side_effect = RuntimeError("postgres://USER:SECRET@HOST")
        result = await self.service()
        self.assertEqual(result["errors"], ["stories_unavailable"])
        self.assertNotIn("SECRET", json.dumps(result["errors"]))
        self.assertEqual(result["drafts"][0]["id"], 7)
        self.assertEqual(result["counts"]["stories_total"], 30)

    async def test_distinct_story_admin_identity_cannot_list_story_review_data(self):
        self.service.admin_id = lambda: 33
        result = await self.service()
        self.assertFalse(result["admin_identity_matches"])
        self.assertEqual(result["stories"], [])
        self.db.get_latest_stories.assert_not_awaited()
        self.assertEqual(result["drafts"][0]["id"], 7)

    async def test_drafts_are_scoped_to_pending_mimosuga_for_current_partner(self):
        good = self.db.get_pending_auto_reply_drafts.return_value[0]
        self.db.get_pending_auto_reply_drafts.return_value += [
            {**good, "id": 8, "incoming_chat_id": 99},
            {**good, "id": 9, "animal_key": "salchicher"},
            {**good, "id": 10, "status": "sent"},
        ]
        result = await self.service()
        self.assertEqual([draft["id"] for draft in result["drafts"]], [7])
        self.db.get_pending_auto_reply_drafts.assert_awaited_once_with(animal_key="mimosuga", chat_id=11, limit=21)
        self.partners["mimosuga"] = None
        self.db.get_pending_auto_reply_drafts.reset_mock()
        self.assertEqual((await self.service())["drafts"], [])
        self.db.get_pending_auto_reply_drafts.assert_not_awaited()

    async def test_lists_are_bounded_and_counts_cover_all_active_schedules(self):
        schedule = self.data["schedules"][0]
        self.data["schedules"] = [{**schedule, "id": f"s{i:03}"} for i in range(25)]
        draft = self.db.get_pending_auto_reply_drafts.return_value[0]
        self.db.get_pending_auto_reply_drafts.return_value = [{**draft, "id": i + 1} for i in range(21)]
        result = await self.service()
        self.assertEqual(len(result["schedules"]), 20)
        self.assertEqual(result["counts"]["schedules_active"], 25)
        self.assertEqual(len(result["drafts"]), 20)
        self.assertTrue(result["truncated"]["schedules"])
        self.assertTrue(result["truncated"]["drafts"])
        self.assertEqual(result["schedules"][0]["id"], "s000")

    async def test_missing_partner_never_falls_back_to_owner_notebook(self):
        self.service.get_vaca_partner = lambda: None
        self.assertEqual((await self.service())["wishes"], [])

    async def test_unknown_dates_and_bad_schedule_stay_explicit(self):
        self.db.get_latest_stories.return_value[0]["created_at"] = None
        self.data["vaca_campaigns"]["plans"]["v1"]["created_at"] = "unknown"
        def invalid_schedule(schedule, now):
            raise ValueError("invalid date")
        self.service.next_schedule = invalid_schedule
        result = await self.service()
        self.assertIsNone(result["stories"][0]["created_at"])
        self.assertIsNone(result["visits"][0]["created_at"])
        self.assertIsNone(result["schedules"][0]["next_at"])


class PendingDraftQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_query_parameterizes_scope_and_bounds_size(self):
        pool = SimpleNamespace(fetch=AsyncMock(return_value=[{"id": 7}]))
        with patch.object(database, "require_pool", return_value=pool):
            result = await database.get_pending_auto_reply_drafts(animal_key="mimosuga", chat_id=11, limit=9999)
        sql, animal, recipient, limit = pool.fetch.await_args.args
        self.assertIn("status = 'pending'", sql)
        self.assertIn("animal_key = $1 and incoming_chat_id = $2", sql)
        self.assertIn("order by created_at desc, id desc", sql)
        self.assertEqual((animal, recipient, limit), ("mimosuga", 11, 100))
        self.assertEqual(result, [{"id": 7}])


if __name__ == "__main__":
    unittest.main()
