import copy
import asyncio
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from history_service import BASELINE_KEY, HistoryService, HistoryUnavailable, RETENTION_SECONDS
from salchicher_copy import LEGACY_GREETING, LEGACY_INTRO, LEGACY_QUESTIONS


STAMP = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)


def event(identity, text, role="assistant", moment=STAMP):
    return {"id": identity, "text": text, "role": role, "time": moment.isoformat(), "source": "telegram"}


class MemoryDatabase:
    def __init__(self):
        self.available = True
        self.rows = []
        self.drafts = []
        self.write_calls = 0
        self.read_calls = 0

    def db_available(self):
        return self.available

    async def archive_conversation_event(self, **value):
        self.write_calls += 1
        if not any((row["chat_id"], row["animal_key"], row["source_key"]) ==
                   (value["chat_id"], value["animal_key"], value["source_key"]) for row in self.rows):
            self.rows.append({"id": len(self.rows) + 1, **value})

    async def get_conversation_archive(self, **query):
        self.read_calls += 1
        rows = [row for row in self.rows if row["chat_id"] == query["chat_id"]
                and row["animal_key"] == query["animal_key"] and row["epoch"] == query["epoch"]]
        def key(row):
            return (row["occurred_at"] is not None, row["occurred_at"] or STAMP, row["source_key"])
        if query["before_key"]:
            bound = (query["before_time"] is not None, query["before_time"] or STAMP, query["before_key"])
            rows = [row for row in rows if key(row) < bound]
        return copy.deepcopy(sorted(rows, key=key, reverse=True)[:query["limit"]])

    async def get_sent_auto_reply_archive(self, **query):
        rows = [row for row in self.drafts if row["chat_id"] == query["chat_id"] and row["recorded_at"] < query["cutover"]]
        known = {f"event:{row['event_id']}": (row["text"], int(row["occurred_at"].timestamp()))
                 for row in self.rows if row["chat_id"] == query["chat_id"] and row["animal_key"] == "mimosuga"
                 and row["epoch"] == 0 and row["role"] == "assistant" and row["occurred_at"] is not None}
        for message in query.get("known_messages", []):
            if message["role"] == "assistant" and message["time"]:
                known[message["identity"]] = (message["text"], int(datetime.fromisoformat(message["time"]).timestamp()))
        counts, ranks, kept = {}, {}, []
        for key in known.values():
            counts[key] = counts.get(key, 0) + 1
        for row in sorted(rows, key=lambda row: row["id"]):
            if row["role"] == "assistant" and row["occurred_at"] is not None:
                key = (row["text"], int(row["occurred_at"].timestamp()))
                ranks[key] = ranks.get(key, 0) + 1
                if ranks[key] <= counts.get(key, 0):
                    continue
            kept.append(row)
        rows = kept
        if query["before_key"]:
            if query["before_time"] is None:
                return []
            rows = [row for row in rows if (row["sort_at"], row["source_key"]) < (query["before_time"], query["before_key"])]
        return copy.deepcopy(sorted(rows, key=lambda row: (row["sort_at"], row["source_key"]), reverse=True)[:query["limit"]])

    async def delete_conversation_archive_before_epoch(self, **query):
        self.rows = [row for row in self.rows if not (row["chat_id"] == query["chat_id"]
                     and row["animal_key"] == query["animal_key"] and row["epoch"] < query["epoch"])]


class HistoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {
            "mimosuga_partner_chat_id": 11,
            "history": {"mimosuga": [{"at": STAMP.isoformat(), "direction": "in", "text": "Hola abuela"},
                                        {"at": (STAMP + timedelta(seconds=1)).isoformat(), "direction": "out", "text": "Hola patita"}]},
            "vaca": {"sessions": {"11": {"history": [{"role": "user", "content": "Libro bonito"}],
                                            "wishes": [{"id": "w1", "name": "Libro"}]},
                                     "22": {"history": [{"role": "user", "content": "Prueba del Oso"}]}}},
            "salchicher": {"sessions": {"11": {"updated_at": time.time(), "history": [{"role": "user", "content": "Privado"}]}}},
            "vaca_campaigns": {"gifts": "REGALO_SECRETO"},
        }
        self.db = MemoryDatabase()
        def save(data):
            self.data = copy.deepcopy(data)
        def partner(animal):
            if animal == "dulcimiel":
                raise KeyError(animal)
            return 11
        self.service = HistoryService(lambda: copy.deepcopy(self.data), save, partner,
            lambda actor: {"sandra": 11, "owner": 22}.get(actor), self.db)

    async def test_doctor_filters_retired_copy_before_pagination_without_rewriting_history(self):
        screening = "Gracias por contármelo, solete. " + LEGACY_QUESTIONS["context"]
        manual = "Nota manual: " + screening
        self.data["salchicher"]["sessions"]["11"]["history"] = [
            {"role": "assistant", "content": LEGACY_GREETING},
            {"role": "user", "content": LEGACY_GREETING},
            {"role": "assistant", "content": screening},
            {"role": "assistant", "content": manual},
        ]
        now = datetime.now(timezone.utc)
        self.data["web_bridge"] = {"inboxes": {"11:salchicher": [
            event(10, LEGACY_INTRO, moment=now),
            event(11, "Una mantita nueva", moment=now + timedelta(seconds=1)),
        ]}}
        await self.service.initialize()
        before = copy.deepcopy(self.data)
        messages, cursor = [], None
        for _ in range(4):
            page = await self.service.page("sandra", 11, "salchicher", before=cursor, limit=1)
            self.assertEqual(len(page["messages"]), 1)
            messages.extend(page["messages"])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
            self.assertIsNotNone(cursor)
        self.assertCountEqual([message["text"] for message in messages],
                              [LEGACY_GREETING, manual, "Una mantita nueva"])
        self.assertEqual(next(message for message in messages if message["text"] == LEGACY_GREETING)["role"], "user")
        self.assertEqual(next(message for message in messages if message["text"] == "Una mantita nueva")["id"], 11)
        self.assertIsNone(cursor)
        self.assertEqual(self.data, before)
        self.assertEqual(self.db.read_calls, 0)

    async def test_baseline_is_once_only_preserves_sources_and_never_snapshots_consultation(self):
        original = copy.deepcopy(self.data)
        await self.service.initialize()
        for key in original:
            self.assertEqual(self.data[key], original[key])
        baseline = copy.deepcopy(self.data[BASELINE_KEY])
        self.assertNotIn("11:salchicher", baseline["scopes"])
        self.assertNotIn("Privado", str(baseline))
        self.assertNotIn("REGALO_SECRETO", str(baseline))
        self.data["history"]["mimosuga"].append({"at": STAMP.isoformat(), "direction": "out", "text": "Nuevo sin archivar"})
        await self.service.initialize()
        self.assertEqual(self.data[BASELINE_KEY], baseline)
        page = await self.service.page("sandra", 11, "mimosuga")
        self.assertEqual([m["text"] for m in page["messages"]], ["Hola abuela", "Hola patita"])

    async def test_unscoped_legacy_requires_concordant_sandra_identity(self):
        self.data["starts"] = {"mimosuga": 999}
        await self.service.initialize()
        self.assertNotIn("11:mimosuga", self.data[BASELINE_KEY]["scopes"])
        self.assertEqual((await self.service.page("owner", 22, "mimosuga"))["messages"], [])
        with self.assertRaises(PermissionError):
            await self.service.page("owner", 11, "mimosuga")
        with self.assertRaises(PermissionError):
            await self.service.page("sandra", 22, "mimosuga")

    async def test_vaca_sessions_are_scoped_and_dates_are_not_invented(self):
        await self.service.initialize()
        sandra = await self.service.page("sandra", 11, "vaca")
        owner = await self.service.page("owner", 22, "vaca")
        self.assertEqual([m["text"] for m in sandra["messages"]], ["Libro bonito"])
        self.assertEqual([m["text"] for m in owner["messages"]], ["Prueba del Oso"])
        self.assertIsNone(sandra["messages"][0]["time"])

    async def test_original_message_ids_shared_across_outbox_inbox_and_database(self):
        item = event(10, "Nueva respuesta", moment=STAMP + timedelta(days=1))
        self.data["web_bridge"] = {"inboxes": {"11:mimosuga": [item]}}
        self.data["history_outbox"] = [{"animal": "mimosuga", "chat_id": 11, "event": item, "epoch": 0}]
        await self.service.initialize()
        await self.service.record_event("mimosuga", 11, item)
        await self.service.record_event("mimosuga", 11, item)
        page = await self.service.page("sandra", 11, "mimosuga")
        mirrored = [m for m in page["messages"] if m["id"] == 10]
        self.assertEqual(len(mirrored), 1)
        self.assertEqual(mirrored[0]["event_id"], 10)
        self.assertEqual(len(self.db.rows), 1)

    async def test_same_text_consecutive_turns_and_same_second_remain_distinct(self):
        self.data["history"]["mimosuga"] = []
        await self.service.initialize()
        for identity in (1, 2, 3):
            await self.service.record_event("mimosuga", 11, event(identity, "Mismo texto"))
        page = await self.service.page("sandra", 11, "mimosuga")
        self.assertEqual([m["id"] for m in page["messages"]], [1, 2, 3])

    async def test_baseline_does_not_duplicate_known_existing_live_message(self):
        self.data["web_bridge"] = {"inboxes": {"11:mimosuga": [event(4, "Hola abuela", "user")]}}
        await self.service.initialize()
        page = await self.service.page("sandra", 11, "mimosuga")
        self.assertEqual([m["text"] for m in page["messages"]].count("Hola abuela"), 1)
        self.assertEqual(page["messages"][0]["id"], 4)

    async def test_history_paginates_beyond_inbox_200_without_gaps(self):
        self.data["history"]["mimosuga"] = []
        await self.service.initialize()
        for identity in range(1, 246):
            await self.service.record_event("mimosuga", 11, event(identity, str(identity), moment=STAMP + timedelta(seconds=identity)))
        collected, cursor = [], None
        for _ in range(30):
            page = await self.service.page("sandra", 11, "mimosuga", before=cursor, limit=13)
            self.assertEqual([m["id"] for m in page["messages"]], sorted(m["id"] for m in page["messages"]))
            collected.extend(m["id"] for m in page["messages"])
            cursor = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(len(collected), 245)
        self.assertEqual(set(collected), set(range(1, 246)))

    async def test_mixed_sources_and_unknown_dates_paginate_without_early_end(self):
        self.data["history"]["mimosuga"] = [
            {"direction": "user", "text": "ignored malformed role"},
            {"direction": "in", "text": "Fecha no guardada"},
            {"at": STAMP.isoformat(), "direction": "out", "text": "Respuesta de antes"},
        ]
        await self.service.initialize()
        for identity in range(1, 8):
            await self.service.record_event("mimosuga", 11, event(identity, f"Nuevo {identity}", moment=STAMP + timedelta(hours=identity)))
        self.db.drafts = [{"id": 90, "chat_id": 11, "source_key": "draft:00000000000000000090:in", "role": "user",
             "text": "- Bloque histórico", "occurred_at": None, "sort_at": STAMP - timedelta(days=1),
             "recorded_at": STAMP - timedelta(days=1)}]
        messages, pages, before = [], [], None
        for _ in range(20):
            page = await self.service.page("sandra", 11, "mimosuga", before=before, limit=2)
            messages.extend(page["messages"])
            pages.append(page["messages"])
            before = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(len(messages), 10)
        self.assertEqual(len({m["id"] for m in messages}), 10)
        unknown = next(m for m in messages if m["text"] == "Fecha no guardada")
        self.assertIsNone(unknown["time"])
        chronology = [message for page in reversed(pages) for message in page]
        self.assertEqual([message["text"] for message in chronology],
                         ["Fecha no guardada", "- Bloque histórico", "Respuesta de antes"]
                         + [f"Nuevo {identity}" for identity in range(1, 8)])

    async def test_cursor_is_scope_bound_and_invalid_cursor_fails_explicitly(self):
        await self.service.initialize()
        page = await self.service.page("sandra", 11, "mimosuga", limit=1)
        for actor, chat_id, animal in (("owner", 22, "mimosuga"), ("sandra", 11, "vaca")):
            with self.assertRaises(ValueError):
                await self.service.page(actor, chat_id, animal, before=page["next_cursor"])
        for before in ("!", "x" * 513, "a", "e30"):
            with self.assertRaises(ValueError):
                await self.service.page("sandra", 11, "mimosuga", before=before)

    async def test_private_consultation_is_only_active_session_and_never_calls_archive(self):
        await self.service.initialize()
        self.db.get_conversation_archive = AsyncMock(side_effect=AssertionError("No private reads"))
        self.db.archive_conversation_event = AsyncMock(side_effect=AssertionError("No private writes"))
        page = await self.service.page("sandra", 11, "salchicher")
        self.assertEqual(page["messages"][0]["text"], "Privado")
        self.assertIsNone(page["messages"][0]["time"])
        self.assertFalse(page["archive_available"])
        self.assertEqual(page["retention"], "active_consultation_48h")
        self.assertTrue(await self.service.record_event("salchicher", 11, event(20, "No guardar")))
        self.assertEqual((await self.service.page("owner", 22, "salchicher"))["messages"], [])
        self.data["salchicher"]["sessions"]["11"]["updated_at"] = time.time() - RETENTION_SECONDS - 1
        self.assertEqual((await self.service.page("sandra", 11, "salchicher"))["messages"], [])
        self.db.get_conversation_archive.assert_not_awaited()
        self.db.archive_conversation_event.assert_not_awaited()

    async def test_private_session_copies_reuse_live_ids_without_collapsing_repeated_turns(self):
        current = datetime.now(timezone.utc)
        self.data["salchicher"]["sessions"]["11"]["history"] = [
            {"role": "user", "content": "Igual"}, {"role": "user", "content": "Igual"}]
        self.data["web_bridge"] = {"inboxes": {"11:salchicher": [event(8, "Igual", "user", current)]}}
        await self.service.initialize()
        page = await self.service.page("sandra", 11, "salchicher")
        self.assertEqual(len(page["messages"]), 2)
        self.assertEqual(page["messages"][-1]["id"], 8)
        self.assertIsNone(page["messages"][0]["time"])

    async def test_forget_epoch_prevents_resurrection_and_preserves_new_messages_and_wishes(self):
        await self.service.initialize()
        await self.service.record_event("vaca", 11, event(1, "Antes"), epoch=0)
        self.data["history_forgets"] = {"11:vaca": {"epoch": 1, "pending": True}}
        self.assertEqual((await self.service.page("sandra", 11, "vaca"))["messages"], [])
        self.assertTrue(await self.service.record_event("vaca", 11, event(2, "Antiguo retrasado"), epoch=0))
        self.assertTrue(await self.service.record_event("vaca", 11, event(3, "Después"), epoch=1))
        self.assertTrue(await self.service.forget("vaca", 11, epoch=1))
        self.assertEqual([row["text"] for row in self.db.rows], ["Después"])
        self.assertNotIn("11:vaca", self.data[BASELINE_KEY]["scopes"])
        self.assertEqual(self.data["vaca"]["sessions"]["11"]["wishes"][0]["name"], "Libro")
        await self.service.initialize()
        self.assertEqual([m["text"] for m in (await self.service.page("sandra", 11, "vaca"))["messages"]], ["Después"])

    async def test_storage_outage_keeps_available_baseline_outbox_and_defers_new_writes(self):
        await self.service.initialize()
        self.db.available = False
        self.data["history_outbox"] = [{"animal": "mimosuga", "chat_id": 11, "event": event(8, "Pendiente"), "epoch": 0}]
        page = await self.service.page("sandra", 11, "mimosuga")
        self.assertFalse(page["archive_available"])
        self.assertIn("Pendiente", [m["text"] for m in page["messages"]])
        self.assertFalse(await self.service.record_event("mimosuga", 11, event(8, "Pendiente")))
        self.db.available = True
        self.db.get_conversation_archive = AsyncMock(side_effect=OSError("PRIVATE_ERROR"))
        with self.assertRaises(HistoryUnavailable):
            await self.service.page("sandra", 11, "mimosuga")

    async def test_forget_during_archive_read_never_returns_stale_private_conversation(self):
        await self.service.initialize()
        entered, release = asyncio.Event(), asyncio.Event()
        async def delayed(**query):
            entered.set()
            await release.wait()
            return [{"id": 1, "event_id": 4, "source_key": "event:00000000000000000004", "source": "telegram",
                     "role": "assistant", "text": "Se acaba de olvidar", "occurred_at": STAMP}]
        self.db.get_conversation_archive = delayed
        pending = asyncio.create_task(self.service.page("sandra", 11, "vaca"))
        await entered.wait()
        self.data["history_forgets"] = {"11:vaca": {"epoch": 1, "pending": True}}
        self.data[BASELINE_KEY]["scopes"].pop("11:vaca", None)
        release.set()
        with self.assertRaises(ValueError):
            await pending

    async def test_old_sent_drafts_preserve_grouped_input_without_invented_received_date(self):
        await self.service.initialize()
        self.db.drafts = [
            {"id": 1, "chat_id": 11, "source_key": "draft:00000000000000000001:in", "role": "user",
             "text": "- Una carta\n- muy antigua", "occurred_at": None, "sort_at": STAMP - timedelta(days=1),
             "recorded_at": STAMP - timedelta(days=1)},
            {"id": 1, "chat_id": 11, "source_key": "draft:00000000000000000001:out", "role": "assistant",
             "text": "Mi respuesta antigua", "occurred_at": STAMP - timedelta(days=1),
             "sort_at": STAMP - timedelta(days=1), "recorded_at": STAMP - timedelta(days=1)},
        ]
        page = await self.service.page("sandra", 11, "mimosuga")
        grouped = next(m for m in page["messages"] if m["id"].__class__ is str and m["id"].endswith(":in"))
        self.assertEqual(grouped["text"], "- Una carta\n- muy antigua")
        self.assertIsNone(grouped["time"])
        self.assertEqual(grouped["recorded_at"], (STAMP - timedelta(days=1)).isoformat())

    async def test_one_known_turn_cannot_hide_two_distinct_grouped_drafts(self):
        await self.service.initialize()
        self.db.drafts = [
            {"id": identity, "chat_id": 11, "source_key": f"draft:{identity:020}:in", "role": "user",
             "text": "- Hola abuela", "occurred_at": None, "sort_at": STAMP + timedelta(minutes=identity),
             "recorded_at": STAMP + timedelta(minutes=identity)}
            for identity in (1, 2)
        ]
        page = await self.service.page("sandra", 11, "mimosuga")
        inputs = [message for message in page["messages"] if message["role"] == "user"]
        self.assertEqual(len(inputs), 3)
        self.assertEqual(sum(message["source"] == "telegram_archive" for message in inputs), 2)
        self.assertTrue(all(message["grouped_input"] for message in inputs if message["source"] == "telegram_archive"))

    async def test_draft_copy_does_not_reappear_after_its_event_on_an_earlier_page(self):
        self.data["history"]["mimosuga"] = []
        await self.service.initialize()
        await self.service.record_event("mimosuga", 11, event(6, "Older", moment=STAMP - timedelta(minutes=1)))
        await self.service.record_event("mimosuga", 11, event(7, "Same reply"))
        self.db.drafts = [{"id": 1, "chat_id": 11, "source_key": "draft:00000000000000000001:out",
            "role": "assistant", "text": "Same reply", "occurred_at": STAMP, "sort_at": STAMP, "recorded_at": STAMP}]
        collected, before = [], None
        while True:
            page = await self.service.page("sandra", 11, "mimosuga", before=before, limit=1)
            collected.extend(page["messages"])
            before = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual([message["id"] for message in collected], [7, 6])

    async def test_many_suppressed_draft_copies_do_not_hide_older_distinct_history(self):
        self.data["history"]["mimosuga"] = []
        await self.service.initialize()
        for identity in range(1, 31):
            await self.service.record_event("mimosuga", 11, event(identity, "Same"))
            self.db.drafts.append({"id": identity, "chat_id": 11, "source_key": f"draft:{identity:020}:out",
                "role": "assistant", "text": "Same", "occurred_at": STAMP, "sort_at": STAMP, "recorded_at": STAMP})
        self.db.drafts.append({"id": 99, "chat_id": 11, "source_key": "draft:00000000000000000099:out",
            "role": "assistant", "text": "Older distinct", "occurred_at": STAMP - timedelta(days=1),
            "sort_at": STAMP - timedelta(days=1), "recorded_at": STAMP - timedelta(days=1)})
        found, before = [], None
        for _ in range(40):
            page = await self.service.page("sandra", 11, "mimosuga", before=before, limit=1)
            found.extend(page["messages"])
            before = page["next_cursor"]
            if not page["has_more"]:
                break
        self.assertEqual(len(found), 31)
        self.assertEqual(found[-1]["text"], "Older distinct")


if __name__ == "__main__":
    unittest.main()
