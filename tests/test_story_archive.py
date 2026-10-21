import copy
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import database
from history_service import HistoryService, HistoryUnavailable


NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)


class StoryStore:
    def __init__(self):
        self.available = True
        self.rows = []
        for number in range(1, 32):
            self.rows.append({"id": number, "delivered_to_user_id": 11, "title": f"Cuento {number}",
                "summary": f"Resumen {number}", "full_text": f"TEXTO COMPLETO ORIGINAL {number}\n" * 250,
                "narrator": "Mimosuga", "created_at": NOW - timedelta(days=number),
                "delivered_at": NOW, "status": "pending" if number % 2 else "canon"})
        self.rows.extend([
            {**self.rows[0], "id": 50, "delivered_to_user_id": 22, "title": "Privado del Oso"},
            {**self.rows[0], "id": 51, "delivered_at": None, "status": "canon", "title": "Nunca entregado"},
        ])

    def db_available(self):
        return self.available

    async def get_delivered_stories(self, *, chat_id, before_time=None, before_id=None, limit=13):
        rows = [row for row in self.rows if row["delivered_to_user_id"] == chat_id and row["delivered_at"] is not None]
        if before_time is not None:
            rows = [row for row in rows if (row["delivered_at"], row["id"]) < (before_time, before_id)]
        return copy.deepcopy(sorted(rows, key=lambda row: (row["delivered_at"], row["id"]), reverse=True)[:limit])

    async def get_delivered_story(self, *, chat_id, story_id):
        return next((copy.deepcopy(row) for row in self.rows if row["id"] == story_id
                     and row["delivered_to_user_id"] == chat_id and row["delivered_at"] is not None), None)


class StoryArchiveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = StoryStore()
        self.service = HistoryService(lambda: {}, lambda data: None, lambda animal: 11,
            lambda actor: {"sandra": 11, "owner": 22}.get(actor), self.db)

    async def test_library_all_delivered_stories_paginates_stably_with_same_dates(self):
        found, cursor = [], None
        while True:
            page = await self.service.stories("sandra", 11, before=cursor, limit=7)
            self.assertTrue(page["archive_available"])
            for row in page["stories"]:
                self.assertEqual(row["delivered_at"], NOW.isoformat())
                self.assertIn("T", row["created_at"])
                self.assertNotIn("full_text", row)
            found.extend(row["id"] for row in page["stories"])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(found, list(range(31, 0, -1)))

    async def test_pending_but_delivered_included_and_undelivered_canon_excluded(self):
        page = await self.service.stories("sandra", 11, limit=50)
        self.assertIn(1, [row["id"] for row in page["stories"]])
        self.assertNotIn(51, [row["id"] for row in page["stories"]])
        self.assertIsNone(await self.service.story("sandra", 11, 51))

    async def test_story_detail_is_full_original_text_and_scoped_by_actor(self):
        result = await self.service.story("sandra", 11, 1)
        self.assertEqual(result["story"]["text"], self.db.rows[0]["full_text"])
        self.assertGreater(len(result["story"]["text"]), 4000)
        self.assertIsNone(await self.service.story("sandra", 11, 50))
        self.assertEqual((await self.service.story("owner", 22, 50))["story"]["title"], "Privado del Oso")
        with self.assertRaises(PermissionError):
            await self.service.story("sandra", 22, 50)

    async def test_story_cursors_are_actor_bound_and_reject_wrong_ids(self):
        page = await self.service.stories("sandra", 11, limit=1)
        with self.assertRaises(ValueError):
            await self.service.stories("owner", 22, before=page["next_cursor"])
        for identity in (0, -1, 2**63, True, "1"):
            with self.assertRaises(ValueError):
                await self.service.story("sandra", 11, identity)

    async def test_library_unavailable_is_explicit_never_a_fake_empty_library(self):
        self.db.available = False
        with self.assertRaises(HistoryUnavailable):
            await self.service.stories("sandra", 11)
        with self.assertRaises(HistoryUnavailable):
            await self.service.story("sandra", 11, 1)
        self.db.available = True
        self.db.get_delivered_stories = AsyncMock(side_effect=OSError("private connection string"))
        with self.assertRaises(HistoryUnavailable) as context:
            await self.service.stories("sandra", 11)
        self.assertNotIn("private connection", str(context.exception))

    async def test_other_delivered_narrators_are_preserved_with_their_true_name(self):
        self.db.rows[0]["narrator"] = "Otra narradora del mundo"
        result = await self.service.story("sandra", 11, 1)
        self.assertEqual(result["story"]["narrator"], "Otra narradora del mundo")


class DatabaseArchiveQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_story_queries_bind_actor_and_require_actual_delivery(self):
        pool = SimpleNamespace(fetch=AsyncMock(return_value=[]), fetchrow=AsyncMock(return_value=None))
        with patch.object(database, "pool", pool):
            await database.get_delivered_stories(chat_id=11, before_time=NOW, before_id=5, limit=13)
            await database.get_delivered_story(chat_id=11, story_id=50)
        query, *arguments = pool.fetch.call_args.args
        self.assertIn("delivered_to_user_id = $1", query)
        self.assertIn("delivered_at is not null", query)
        self.assertIn("order by delivered_at desc, id desc", query)
        self.assertEqual(arguments, [11, NOW, 5, 13])
        query, *arguments = pool.fetchrow.call_args.args
        self.assertIn("delivered_to_user_id = $2", query)
        self.assertIn("delivered_at is not null", query)
        self.assertEqual(arguments, [50, 11])
        self.assertNotIn("status = 'canon'", query)

    async def test_sent_draft_recovery_filters_actor_cutover_and_confirmed_sends(self):
        pool = SimpleNamespace(fetch=AsyncMock(return_value=[]))
        with patch.object(database, "pool", pool):
            await database.get_sent_auto_reply_archive(chat_id=11, cutover=NOW, limit=12)
        query, *arguments = pool.fetch.call_args.args
        self.assertIn("incoming_chat_id = $1", query)
        self.assertIn("animal_key = 'mimosuga'", query)
        self.assertIn("status = 'sent'", query)
        self.assertIn("sent_at is not null", query)
        self.assertIn("created_at < $2", query)
        self.assertIn("sent_at < $2", query)
        self.assertIn("null::timestamptz as occurred_at", query)
        self.assertIn("row_number() over", query)
        self.assertIn("overlap_rank > coalesce", query)
        self.assertIn("chat_id = $1 and animal_key = 'mimosuga' and epoch = 0", query)
        self.assertEqual(arguments[:2], [11, NOW])

    async def test_journal_is_idempotent_epoch_scoped_and_refuses_private_consultations(self):
        pool = SimpleNamespace(execute=AsyncMock(), fetch=AsyncMock(return_value=[]))
        values = {"chat_id": 11, "animal_key": "mimosuga", "source_key": "event:1", "event_id": 1,
                  "source": "telegram", "role": "assistant", "text": "Original", "occurred_at": NOW, "epoch": 0}
        with patch.object(database, "pool", pool):
            await database.archive_conversation_event(**values)
            query = pool.execute.call_args.args[0]
            self.assertIn("on conflict (chat_id, animal_key, source_key) do nothing", query)
            pool.execute.reset_mock()
            with self.assertRaises(ValueError):
                await database.archive_conversation_event(**{**values, "animal_key": "salchicher"})
            pool.execute.assert_not_awaited()
            await database.get_conversation_archive(chat_id=11, animal_key="vaca", epoch=2, before_key="event:1")
            query, *arguments = pool.fetch.call_args.args
            self.assertIn("chat_id = $1 and animal_key = $2 and epoch = $3", query)
            self.assertIn("occurred_at is null and source_key < $5", query)
            self.assertIn("order by occurred_at desc nulls last, source_key desc", query)
            self.assertEqual(arguments[:3], [11, "vaca", 2])
            await database.delete_conversation_archive_before_epoch(chat_id=11, animal_key="vaca", epoch=2)
            self.assertIn("epoch < $3", pool.execute.call_args.args[0])

    async def test_migration_only_adds_journal_and_indexes_with_private_constraint(self):
        conn = SimpleNamespace(execute=AsyncMock())
        class Acquire:
            async def __aenter__(self):
                return conn
            async def __aexit__(self, *args):
                return False
        with patch.object(database, "pool", SimpleNamespace(acquire=lambda: Acquire())):
            await database.migrate()
        sql = conn.execute.call_args.args[0].lower()
        journal = sql.split("create table if not exists conversation_messages", 1)[1]
        self.assertIn("unique (chat_id, animal_key, source_key)", journal)
        self.assertNotIn("'salchicher'", journal)
        self.assertIn("stories_delivered_library_idx", journal)
        self.assertNotIn("drop ", sql)


if __name__ == "__main__":
    unittest.main()
