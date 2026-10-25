"""Unread tracking and scheduled notifications, entirely offline."""

import asyncio
import copy
import json
import time
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from unread_notifications import (
    NOTICE_TEXT, STORE_KEY, UnreadNotifier, acknowledge, forget, initialize,
    latest, pending, record, summary,
)
from salchicher_copy import LEGACY_GREETING, LEGACY_QUESTIONS


def event(identity, animal="mimosuga", **values):
    return {"id": identity, "animal": animal, "role": "assistant",
            "text": "PRIVATE MESSAGE BODY", "timestamp": time.time(), **values}


def add(data, identity, animal="mimosuga", chat_id=11, **values):
    item = event(identity, animal, **values)
    data.setdefault("web_bridge", {}).setdefault("inboxes", {}).setdefault(f"{chat_id}:{animal}", []).append(item)
    record(data, chat_id, animal, item)
    return item


class UnreadLedgerTests(unittest.TestCase):
    def setUp(self):
        self.data = {}
        initialize(self.data)

    def test_initialization_baselines_old_events_once_without_text(self):
        data = {"web_bridge": {"inboxes": {"11:mimosuga": [event(1), event(2)]}}}
        self.assertTrue(initialize(data))
        self.assertFalse(pending(data, 11))
        add(data, 3)
        self.assertFalse(initialize(data))
        self.assertEqual(pending(data, 11), [{"animal": "mimosuga", "event_id": 3}])
        self.assertNotIn("PRIVATE MESSAGE BODY", json.dumps(data[STORE_KEY]))

    def test_scope_identity_roles_and_monotonic_ack(self):
        add(self.data, 1)
        add(self.data, 2)
        add(self.data, 3, chat_id=22)
        add(self.data, 4, animal="vaca")
        add(self.data, 5, role="user")
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", 5))
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", 3))
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", 999999))
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", True))
        self.assertFalse(acknowledge(self.data, True, "mimosuga", 1))
        self.assertEqual(latest(self.data, 11, "mimosuga"), 2)
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 2))
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 1))
        self.assertEqual(pending(self.data, 11), [{"animal": "vaca", "event_id": 4}])
        self.assertEqual(pending(self.data, 22), [{"animal": "mimosuga", "event_id": 3}])

    def test_concurrent_new_event_is_not_acknowledged_by_old_cursor(self):
        add(self.data, 10)
        shown = latest(self.data, 11, "mimosuga")
        add(self.data, 11)
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", shown))
        self.assertEqual(pending(self.data, 11), [{"animal": "mimosuga", "event_id": 11}])

    def test_trimmed_inbox_can_ack_latest_metadata_but_not_unknown_cursor(self):
        add(self.data, 10)
        self.data["web_bridge"]["inboxes"]["11:mimosuga"] = []
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", 9))
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 10))
        self.assertFalse(pending(self.data, 11))

    def test_unread_count_and_partial_ack_survive_full_inbox_trimming(self):
        for identity in range(1, 101):
            add(self.data, identity)
        self.assertEqual(summary(self.data, 11)["total_messages"], 100)
        for identity in range(101, 301):
            add(self.data, identity, role="user")
        self.data["web_bridge"]["inboxes"]["11:mimosuga"] = self.data["web_bridge"]["inboxes"]["11:mimosuga"][-200:]
        self.assertEqual(summary(self.data, 11)["total_messages"], 100)
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 40))
        self.assertEqual(summary(self.data, 11)["total_messages"], 60)
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 40))
        self.assertEqual(summary(self.data, 11)["total_messages"], 60)
        self.assertFalse(acknowledge(self.data, 11, "mimosuga", 101))
        add(self.data, 301)
        self.assertEqual(summary(self.data, 11)["total_messages"], 61)
        self.assertTrue(acknowledge(self.data, 11, "mimosuga", 100))
        self.assertEqual(summary(self.data, 11)["total_messages"], 1)
        self.assertEqual(pending(self.data, 11), [{"animal": "mimosuga", "event_id": 301}])
        self.assertNotIn("PRIVATE MESSAGE BODY", json.dumps(self.data[STORE_KEY]))

    def test_legacy_migration_preserves_baselines_and_delivery_reservations(self):
        data = {STORE_KEY: {"version": 1, "scopes": {
            "11:mimosuga": {"_": {"latest_id": 8, "read_id": 5, "latest_at": time.time()}},
            "11:castori": {"_": {"latest_id": 9, "read_id": 9, "latest_at": time.time()}},
        }, "deliveries": {"previous-slot": {"status": "sent"}}},
            "web_bridge": {"inboxes": {
                "11:mimosuga": [event(2), event(5), event(6), event(8)],
                "11:castori": [event(9, "castori")],
            }}}
        before = copy.deepcopy(pending(data, 11))
        self.assertTrue(initialize(data))
        self.assertFalse(initialize(data))
        self.assertEqual(pending(data, 11), before)
        self.assertEqual(summary(data, 11)["total_messages"], 2)
        entry = data[STORE_KEY]["scopes"]["11:mimosuga"]["_"]
        self.assertEqual((entry["read_id"], entry["latest_id"], entry["pending_ids"]), (5, 8, [6, 8]))
        self.assertEqual(data[STORE_KEY]["scopes"]["11:castori"]["_"]["pending_ids"], [])
        self.assertEqual(data[STORE_KEY]["deliveries"], {"previous-slot": {"status": "sent"}})
        self.assertNotIn("PRIVATE MESSAGE BODY", json.dumps(data[STORE_KEY]))

    def test_legacy_trimmed_cursor_keeps_existing_pending_without_inventing_ids(self):
        data = {STORE_KEY: {"version": 1, "scopes": {
            "11:mimosuga": {"_": {"latest_id": 200, "read_id": 20, "latest_at": time.time()}}}, "deliveries": {}}}
        self.assertTrue(initialize(data))
        self.assertEqual(data[STORE_KEY]["scopes"]["11:mimosuga"]["_"]["pending_ids"], [200])
        self.assertEqual(summary(data, 11)["total_messages"], 1)
        self.assertFalse(acknowledge(data, 11, "mimosuga", 100))
        self.assertTrue(acknowledge(data, 11, "mimosuga", 200))
        self.assertEqual(summary(data, 11)["total_messages"], 0)

    def test_legacy_retired_latest_is_not_reintroduced_after_migration_and_trim(self):
        data = {STORE_KEY: {"version": 1, "scopes": {
            "11:salchicher": {"kept": {"latest_id": 2, "read_id": 0, "latest_at": time.time()}}}, "deliveries": {}},
            "salchicher": {"consultations": {"11": {"kept": {"retained": True}}}},
            "web_bridge": {"inboxes": {"11:salchicher": [
                event(1, "salchicher", consultation_id="kept"),
                event(2, "salchicher", consultation_id="kept", text=LEGACY_GREETING),
            ]}}}
        self.assertTrue(initialize(data))
        self.assertEqual(data[STORE_KEY]["scopes"]["11:salchicher"]["kept"]["pending_ids"], [1])
        data["web_bridge"]["inboxes"]["11:salchicher"] = []
        self.assertEqual(pending(data, 11), [{"animal": "salchicher", "event_id": 1, "consultation_id": "kept"}])
        self.assertEqual(summary(data, 11)["total_messages"], 1)

    def test_first_initialization_marks_historical_ids_read_not_pending(self):
        data = {"web_bridge": {"inboxes": {"11:mimosuga": [event(1), event(2), event(3)]}}}
        initialize(data)
        entry = data[STORE_KEY]["scopes"]["11:mimosuga"]["_"]
        self.assertEqual((entry["read_id"], entry["pending_ids"]), (3, []))
        self.assertEqual(summary(data, 11)["total_messages"], 0)
        add(data, 4)
        self.assertEqual(summary(data, 11)["total_messages"], 1)

    def test_duplicate_and_edit_do_not_increment_persistent_count(self):
        original = add(self.data, 1)
        self.assertFalse(record(self.data, 11, "mimosuga", original))
        self.assertFalse(record(self.data, 11, "mimosuga", {**original, "revision": 999}))
        add(self.data, 2)
        self.assertEqual(summary(self.data, 11)["total_messages"], 2)
        acknowledge(self.data, 11, "mimosuga", 1)
        self.assertFalse(record(self.data, 11, "mimosuga", original))
        self.assertEqual(summary(self.data, 11)["total_messages"], 1)

    def test_retained_doctor_ids_survive_trimming_without_reviving_retired_copy(self):
        self.data["salchicher"] = {"consultations": {"11": {"kept": {"retained": True}}}}
        add(self.data, 1, "salchicher", consultation_id="kept", text="Una nota del doctor")
        add(self.data, 2, "salchicher", consultation_id="kept", text=LEGACY_GREETING)
        add(self.data, 3, "salchicher", consultation_id="kept", text="Otra nota del doctor")
        self.assertEqual(summary(self.data, 11)["total_messages"], 2)
        self.data["web_bridge"]["inboxes"]["11:salchicher"] = []
        self.assertEqual(summary(self.data, 11)["total_messages"], 2)
        self.assertTrue(acknowledge(self.data, 11, "salchicher", 1, "kept"))
        self.assertEqual(summary(self.data, 11)["total_messages"], 1)
        self.assertFalse(acknowledge(self.data, 11, "salchicher", 1, "other"))
        del self.data["salchicher"]["consultations"]["11"]["kept"]
        self.assertEqual(summary(self.data, 11)["total_messages"], 0)

    def test_expired_general_doctor_ids_do_not_inflate_fresh_letter_count(self):
        add(self.data, 1, "salchicher", timestamp=time.time() - 49 * 3600)
        add(self.data, 2, "salchicher")
        self.assertEqual(summary(self.data, 11)["total_messages"], 1)
        self.data["web_bridge"]["inboxes"]["11:salchicher"] = []
        self.assertEqual(summary(self.data, 11)["total_messages"], 0)

    def test_duplicate_and_keyboard_revision_do_not_reopen_read_event(self):
        item = add(self.data, 2)
        acknowledge(self.data, 11, "mimosuga", 2)
        self.assertFalse(record(self.data, 11, "mimosuga", {**item, "revision": 99}))
        self.assertFalse(pending(self.data, 11))

    def test_forget_is_scoped_and_new_message_is_unread(self):
        add(self.data, 1)
        add(self.data, 2, animal="vaca")
        add(self.data, 3, chat_id=22)
        self.assertTrue(forget(self.data, 11, "mimosuga"))
        self.assertFalse(forget(self.data, 11, "mimosuga"))
        self.assertEqual(len(pending(self.data, 11)), 1)
        self.assertEqual(len(pending(self.data, 22)), 1)
        add(self.data, 4)
        self.assertEqual(len(pending(self.data, 11)), 2)

    def test_consultations_require_same_episode_ack_and_exclude_deleted_expired(self):
        now = time.time()
        self.data["salchicher"] = {"sessions": {"11": {"consultation_id": "temporary", "updated_at": now}},
            "consultations": {"11": {"retained": {"retained": True, "status": "recovered"}}}}
        add(self.data, 1, "salchicher", consultation_id="temporary")
        add(self.data, 2, "salchicher", consultation_id="retained")
        add(self.data, 3, "salchicher", consultation_id="deleted")
        self.assertEqual(len(pending(self.data, 11)), 2)
        self.assertEqual(latest(self.data, 11, "salchicher", "temporary"), 1)
        self.assertFalse(acknowledge(self.data, 11, "salchicher", 2, "temporary"))
        self.assertFalse(acknowledge(self.data, 11, "salchicher", 1))
        self.data["salchicher"]["sessions"]["11"]["updated_at"] = now - 49 * 3600
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 2, "consultation_id": "retained"}])
        del self.data["salchicher"]["consultations"]["11"]["retained"]
        self.assertFalse(pending(self.data, 11))

    def test_legacy_doctor_session_is_not_rebound_to_new_consultation(self):
        self.data["salchicher"] = {"sessions": {"11": {"updated_at": time.time()}}}
        add(self.data, 1, "salchicher", requires_consultation=True)
        self.assertEqual(len(pending(self.data, 11)), 1)
        self.data["salchicher"]["sessions"]["11"]["consultation_id"] = "new"
        self.assertFalse(pending(self.data, 11))

    def test_general_doctor_note_counts_without_consultation(self):
        add(self.data, 1, "salchicher")
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 1}])
        self.assertTrue(acknowledge(self.data, 11, "salchicher", 1))
        self.assertFalse(pending(self.data, 11))

    def test_retired_doctor_copy_never_leaves_a_phantom_pending_but_new_visible_copy_does(self):
        screening = "Gracias por contármelo, solete. " + LEGACY_QUESTIONS["context"]
        for sub in (None, "temporary", "retained"):
            with self.subTest(sub=sub):
                data = {"salchicher": {"sessions": {"11": {
                    "consultation_id": "temporary", "updated_at": time.time()}},
                    "consultations": {"11": {"retained": {"retained": True}}}}}
                initialize(data)
                values = {"consultation_id": sub} if sub else {}
                add(data, 1, "salchicher", text=screening, **values)
                before = copy.deepcopy(data)
                self.assertFalse(pending(data, 11))
                self.assertEqual(data, before)
                self.assertEqual(latest(data, 11, "salchicher", sub), 1)
                add(data, 2, "salchicher", text="Te dejo una mantita nueva", **values)
                expected = {"animal": "salchicher", "event_id": 2, **values}
                self.assertEqual(pending(data, 11), [expected])
                self.assertTrue(acknowledge(data, 11, "salchicher", 1, sub))
                self.assertEqual(pending(data, 11), [expected])
                self.assertTrue(acknowledge(data, 11, "salchicher", 2, sub))
                self.assertFalse(pending(data, 11))

    def test_hidden_latest_preserves_earlier_visible_unread_and_unchanged_read_metadata(self):
        add(self.data, 1, "salchicher", text="Una nota pendiente")
        add(self.data, 2, "salchicher", text=LEGACY_GREETING)
        before = copy.deepcopy(self.data)
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 1}])
        self.assertEqual(self.data, before)
        self.assertTrue(acknowledge(self.data, 11, "salchicher", 1))
        self.assertFalse(pending(self.data, 11))
        self.assertEqual(latest(self.data, 11, "salchicher"), 2)
        self.assertEqual(self.data[STORE_KEY]["scopes"]["11:salchicher"]["_"]["read_id"], 1)
        add(self.data, 3, "salchicher", text="Otra nota nueva")
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 3}])

    def test_baseline_retired_copy_stays_read_and_similar_manual_copy_stays_unread(self):
        data = {"web_bridge": {"inboxes": {"11:salchicher": [event(1, "salchicher", text=LEGACY_GREETING)]}}}
        initialize(data)
        before = copy.deepcopy(data)
        self.assertFalse(pending(data, 11))
        self.assertEqual(data, before)
        add(data, 2, "salchicher", text="Nota manual: " + LEGACY_GREETING)
        self.assertEqual(pending(data, 11), [{"animal": "salchicher", "event_id": 2}])

    def test_hidden_latest_does_not_revive_an_expired_visible_general_note(self):
        add(self.data, 1, "salchicher", text="Nota ya caducada", timestamp=time.time() - 49 * 3600)
        add(self.data, 2, "salchicher", text=LEGACY_GREETING)
        self.assertFalse(pending(self.data, 11))

    def test_new_consultation_does_not_consume_general_doctor_note(self):
        add(self.data, 1, "salchicher")
        self.data["salchicher"] = {"sessions": {"11": {
            "consultation_id": "new-episode", "updated_at": time.time()}}}
        add(self.data, 2, "salchicher", consultation_id="new-episode", requires_consultation=True)
        self.assertTrue(acknowledge(self.data, 11, "salchicher", 2, "new-episode"))
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 1}])

    def test_expired_or_removed_general_note_does_not_count_even_with_active_session(self):
        self.data["salchicher"] = {"sessions": {"11": {"updated_at": time.time()}}}
        add(self.data, 1, "salchicher", timestamp=time.time() - 49 * 3600)
        self.assertFalse(pending(self.data, 11))
        add(self.data, 2, "salchicher")
        self.assertEqual(len(pending(self.data, 11)), 1)
        self.data["web_bridge"]["inboxes"]["11:salchicher"] = []
        self.assertFalse(pending(self.data, 11))

    def test_legacy_doctor_message_still_requires_unexpired_session(self):
        add(self.data, 1, "salchicher", requires_consultation=True)
        self.assertFalse(pending(self.data, 11))
        self.data["salchicher"] = {"sessions": {"11": {"updated_at": time.time() - 49 * 3600}}}
        self.assertFalse(pending(self.data, 11))
        self.data["salchicher"]["sessions"]["11"]["updated_at"] = time.time()
        self.assertEqual(pending(self.data, 11), [{"animal": "salchicher", "event_id": 1}])


class UnreadNotifierTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.data = {}
        initialize(self.data)
        self.bot = SimpleNamespace(send_notification=AsyncMock())
        self.identities = {"sandra": 11, "owner": 22}
        self.save_count = 0

        def save(data):
            self.save_count += 1
            self.data = copy.deepcopy(data)

        self.save = save
        self.notifier = self.new_notifier()

    def new_notifier(self, save=None):
        return UnreadNotifier(lambda: copy.deepcopy(self.data), save or self.save,
                              self.identities.get, lambda: self.bot, "https://house.example/castori/index.html")

    async def test_retired_copy_does_not_notify_but_a_later_visible_message_does(self):
        add(self.data, 1, "salchicher", text=LEGACY_GREETING)
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 6, tzinfo=timezone.utc)), "no_unread")
        self.bot.send_notification.assert_not_awaited()
        add(self.data, 2, "salchicher", text="Te he preparado una mantita")
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 18, tzinfo=timezone.utc)), "sent")
        self.bot.send_notification.assert_awaited_once()

    async def test_madrid_winter_and_summer_slots_and_window(self):
        add(self.data, 1)
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 5, 59, tzinfo=timezone.utc)), "skipped")
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 6, 0, tzinfo=timezone.utc)), "sent")
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 18, 14, tzinfo=timezone.utc)), "sent")
        self.assertEqual(await self.notifier.tick(datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc)), "sent")
        self.assertEqual(await self.notifier.tick(datetime(2026, 6, 1, 17, 0, tzinfo=timezone.utc)), "sent")
        self.assertEqual(await self.notifier.tick(datetime(2026, 6, 2, 5, 15, tzinfo=timezone.utc)), "skipped")
        self.assertEqual(await self.notifier.tick(datetime(2026, 6, 2, 22, 0, tzinfo=timezone.utc)), "skipped")
        self.assertEqual(self.bot.send_notification.await_count, 4)
        kwargs = self.bot.send_notification.await_args.kwargs
        self.assertEqual(kwargs["chat_id"], 11)
        self.assertEqual(kwargs["text"], NOTICE_TEXT)
        self.assertEqual(kwargs["reply_markup"].inline_keyboard[0][0].url, "https://house.example/castori/index.html")
        self.assertNotIn("PRIVATE MESSAGE BODY", kwargs["text"])

    async def test_restart_and_simultaneous_ticks_do_not_repeat_reserved_slot(self):
        add(self.data, 1)
        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        self.assertEqual(await self.notifier.tick(instant), "sent")
        self.assertEqual(await self.new_notifier().tick(instant), "skipped")
        next_slot = datetime(2026, 1, 1, 18, tzinfo=timezone.utc)
        statuses = await asyncio.gather(self.notifier.tick(next_slot), self.new_notifier().tick(next_slot))
        self.assertCountEqual(statuses, ["sent", "skipped"])
        self.assertEqual(self.bot.send_notification.await_count, 2)

    async def test_no_unread_marks_slot_so_later_arrival_waits_until_evening(self):
        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        self.assertEqual(await self.notifier.tick(instant), "no_unread")
        add(self.data, 1)
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 6, 3, tzinfo=timezone.utc)), "skipped")
        self.bot.send_notification.assert_not_awaited()
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 18, tzinfo=timezone.utc)), "sent")

    async def test_ambiguous_delivery_is_not_retried_after_restart(self):
        add(self.data, 1)
        self.bot.send_notification.side_effect = TimeoutError("offline test")
        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        self.assertEqual(await self.notifier.tick(instant), "uncertain")
        self.assertEqual(await self.new_notifier().tick(instant), "skipped")
        self.bot.send_notification.assert_awaited_once()
        self.assertEqual(next(iter(self.data[STORE_KEY]["deliveries"].values()))["status"], "uncertain")

    async def test_failed_reservation_never_sends(self):
        add(self.data, 1)

        def fail_save(_):
            raise OSError("offline disk failure")

        self.assertEqual(await self.new_notifier(fail_save).tick(datetime(2026, 1, 1, 6, tzinfo=timezone.utc)), "unavailable")
        self.bot.send_notification.assert_not_awaited()
        self.assertFalse(self.data[STORE_KEY]["deliveries"])

    async def test_success_followed_by_receipt_save_failure_does_not_repeat(self):
        add(self.data, 1)

        def save_once(data):
            if self.save_count:
                raise OSError("offline disk failure")
            self.save(data)

        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        self.assertEqual(await self.new_notifier(save_once).tick(instant), "sent")
        self.assertEqual(await self.new_notifier().tick(instant), "skipped")
        self.bot.send_notification.assert_awaited_once()

    async def test_read_and_new_event_during_delivery_survive_final_save(self):
        add(self.data, 1)

        async def sending(**_):
            self.assertEqual(next(iter(self.data[STORE_KEY]["deliveries"].values()))["status"], "sending")
            acknowledge(self.data, 11, "mimosuga", 1)
            add(self.data, 2)

        self.bot.send_notification.side_effect = sending
        self.assertEqual(await self.notifier.tick(datetime(2026, 1, 1, 6, tzinfo=timezone.utc)), "sent")
        self.assertEqual(pending(self.data, 11), [{"animal": "mimosuga", "event_id": 2}])
        self.assertEqual(self.data[STORE_KEY]["scopes"]["11:mimosuga"]["_"]["read_id"], 1)

    async def test_sandra_only_no_fallback_or_other_house_notifications(self):
        add(self.data, 1, chat_id=22)
        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        self.assertEqual(await self.notifier.tick(instant), "no_unread")
        for invalid in (None, 0, True, 22):
            self.identities["sandra"] = invalid
            self.assertEqual(await self.notifier.tick(instant), "unavailable")
        self.bot.send_notification.assert_not_awaited()

    async def test_cancellation_preserves_reservation(self):
        add(self.data, 1)
        self.bot.send_notification.side_effect = asyncio.CancelledError
        instant = datetime(2026, 1, 1, 6, tzinfo=timezone.utc)
        with self.assertRaises(asyncio.CancelledError):
            await self.notifier.tick(instant)
        self.assertEqual(await self.new_notifier().tick(instant), "skipped")
        self.bot.send_notification.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
