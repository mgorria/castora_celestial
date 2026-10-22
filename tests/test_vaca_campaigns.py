import asyncio
import copy
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from vaca_campaigns import VacaCampaigns, public_chat_anticipation


MADRID = ZoneInfo("Europe/Madrid")
MESSAGES = {"clues": ["He encontrado una cinta misteriosa.", "Mis pezuñas guardan un secreto."],
            "morning": "He dejado un poco de magia junto al árbol."}


def update(text, chat_type="private"):
    return SimpleNamespace(effective_chat=SimpleNamespace(type=chat_type, send_message=AsyncMock()),
                           message=SimpleNamespace(text=text))


class ChatAnticipationTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 12, 3, 12, tzinfo=MADRID)
        self.plan = {"id": "PRIVATE-ID", "status": "active", "recipient_id": 2,
            "gifts": "PRIVATE-GIFTS", "delivery_at": "2026-12-10T08:00:00+01:00",
            "events": {"pista1": {"status": "sent", "text": "DELIVERED CLUE"},
                       "pista2": {"status": "pending", "text": "FUTURE CLUE"},
                       "manana": {"status": "pending", "text": "FUTURE GREETING"}}}
        self.data = {"vaca_campaigns": {"paused": False, "plans": {"PRIVATE-ID": self.plan}}}

    def test_only_active_recipient_gets_permission_and_no_private_metadata(self):
        before = copy.deepcopy(self.data)
        self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": True, "arrival_near": False})
        self.assertEqual(public_chat_anticipation(self.data, 1, now=self.now), {"visit_active": False, "arrival_near": False})
        self.assertEqual(self.data, before)

    def test_unactivated_cancelled_completed_or_expired_visit_never_builds_expectation(self):
        for status in ["draft", "cancelled", "completed"]:
            with self.subTest(status=status):
                self.plan["status"] = status
                self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})
        self.plan["status"] = "active"
        self.assertEqual(public_chat_anticipation(self.data, 2,
            now=datetime(2026, 12, 11, 12, tzinfo=MADRID)), {"visit_active": False, "arrival_near": False})

    def test_pause_and_ambiguous_or_delivered_morning_disable_anticipation(self):
        self.data["schedules_paused"] = True
        self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})
        self.data["schedules_paused"] = False
        self.data["vaca_campaigns"]["paused"] = True
        self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})
        self.data["vaca_campaigns"]["paused"] = False
        for status in ["sent", "sending", "uncertain", "expired", "cancelled"]:
            with self.subTest(status=status):
                self.plan["events"]["manana"]["status"] = status
                self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})

    def test_nearness_is_only_a_boolean_within_72_hours_and_never_a_date(self):
        for now, near in [(datetime(2026, 12, 7, 7, 59, tzinfo=MADRID), False),
                          (datetime(2026, 12, 7, 8, 0, tzinfo=MADRID), True),
                          (datetime(2026, 12, 10, 7, 59, tzinfo=MADRID), True)]:
            with self.subTest(now=now):
                self.assertEqual(public_chat_anticipation(self.data, 2, now=now),
                                 {"visit_active": True, "arrival_near": near})
        self.assertEqual(public_chat_anticipation(self.data, 2,
            now=datetime(2026, 12, 10, 8, 0, tzinfo=MADRID)), {"visit_active": False, "arrival_near": False})

    def test_near_visit_is_found_even_after_a_distant_active_plan(self):
        distant = copy.deepcopy(self.plan)
        distant["delivery_at"] = "2026-12-30T08:00:00+01:00"
        self.data["vaca_campaigns"]["plans"] = {"far": distant, "near": self.plan}
        self.assertEqual(public_chat_anticipation(self.data, 2,
            now=datetime(2026, 12, 9, 8, tzinfo=MADRID)), {"visit_active": True, "arrival_near": True})

    def test_malformed_dates_and_recipient_fail_closed(self):
        for value in [None, "invalid", "2026-12-10T08:00:00"]:
            with self.subTest(value=value):
                self.plan["delivery_at"] = value
                self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})
        self.plan["delivery_at"] = "2026-12-10T08:00:00+01:00"
        self.plan["recipient_id"] = "2"
        self.assertEqual(public_chat_anticipation(self.data, 2, now=self.now), {"visit_active": False, "arrival_near": False})


class CampaignTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"other": {"keep": True}}
        self.recipient = 2
        self.global_pause = False
        self.send, self.notify = AsyncMock(), AsyncMock()
        self.bot = self.new_bot()
        self.now = datetime(2026, 12, 1, 9, 0, tzinfo=MADRID)
        self.bot.now = lambda: self.now

    def new_bot(self):
        def save(data):
            self.data = copy.deepcopy(data)
        return VacaCampaigns(lambda: copy.deepcopy(self.data), save, lambda: self.recipient,
                             self.send, self.notify, MADRID, lambda: self.global_pause)

    async def command(self, text):
        incoming = update(text)
        await self.bot.handle_admin(incoming, None)
        return incoming

    async def create(self, when="10/12/2026 08:00"):
        with patch("vaca_campaigns.generate_visit_messages", AsyncMock(return_value=MESSAGES)):
            await self.command(f"/vaca_visita {when} | un libro y unos calcetines")
        return list(self.data["vaca_campaigns"]["plans"])[-1]

    def plan(self, plan_id):
        return self.data["vaca_campaigns"]["plans"][plan_id]

    async def activate(self, plan_id):
        await self.command(f"/vaca_activar {plan_id}")

    async def test_private_preview_draft_does_not_send(self):
        pid = await self.create()
        plan = self.plan(pid)
        self.assertEqual(plan["status"], "draft")
        self.assertEqual(plan["events"]["pista1"]["at"], "2026-12-07T18:00:00+01:00")
        self.assertEqual(plan["events"]["pista2"]["at"], "2026-12-09T18:00:00+01:00")
        await self.bot.tick(datetime(2026, 12, 10, 8, tzinfo=MADRID))
        self.send.assert_not_awaited()
        self.assertEqual(self.data["other"], {"keep": True})

    async def test_utc_and_madrid_represent_same_due_instant(self):
        pid = await self.create()
        await self.activate(pid)
        await self.bot.tick(datetime(2026, 12, 7, 16, 59, tzinfo=timezone.utc))
        self.send.assert_not_awaited()
        await self.bot.tick(datetime(2026, 12, 7, 17, 0, tzinfo=timezone.utc))
        self.send.assert_awaited_once_with(2, MESSAGES["clues"][0])
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "sent")
        with self.assertRaises(ValueError):
            await self.bot.tick(datetime(2026, 12, 7, 18))

    async def test_near_visits_skip_past_or_november_clues(self):
        for when in ["01/12/2026 10:00", "02/12/2026 08:00"]:
            pid = await self.create(when)
            self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "skipped")
        first = list(self.data["vaca_campaigns"]["plans"])[0]
        self.assertEqual(self.plan(first)["events"]["pista2"]["status"], "skipped")
        await self.activate(first)
        await self.bot.tick(datetime(2026, 12, 1, 10, tzinfo=MADRID))
        self.send.assert_awaited_once_with(2, MESSAGES["morning"])

    async def test_invalid_month_past_and_failed_generation_create_nothing(self):
        for when in ["30/11/2026 23:59", "01/12/2026 08:59", "01/01/2027 08:00"]:
            await self.command(f"/vaca_visita {when} | libro")
        self.assertNotIn("vaca_campaigns", self.data)
        for generated in [RuntimeError("private error"), {"clues": ["one"], "morning": "hello"}]:
            mock = AsyncMock(side_effect=generated) if isinstance(generated, Exception) else AsyncMock(return_value=generated)
            with patch("vaca_campaigns.generate_visit_messages", mock):
                incoming = await self.command("/vaca_visita 10/12/2026 08:00 | libro")
            self.assertNotIn("vaca_campaigns", self.data)
            self.assertNotIn("private error", incoming.effective_chat.send_message.call_args.args[0])

    async def test_activation_requires_started_recipient_and_captures_it(self):
        pid = await self.create()
        self.recipient = None
        await self.activate(pid)
        self.assertEqual(self.plan(pid)["status"], "draft")
        self.recipient = 2
        await self.activate(pid)
        self.assertEqual(self.plan(pid)["recipient_id"], 2)
        self.recipient = 99
        await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.send.assert_not_awaited()
        self.assertEqual(self.plan(pid)["status"], "draft")
        self.notify.assert_awaited_once()

    async def test_late_event_expires_once_and_is_not_replayed(self):
        pid = await self.create()
        await self.activate(pid)
        late = datetime(2026, 12, 7, 20, 1, tzinfo=MADRID)
        await self.bot.tick(late)
        await self.bot.tick(late)
        self.send.assert_not_awaited()
        self.notify.assert_awaited_once()
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "expired")

    async def test_send_error_and_restart_reservation_never_replay(self):
        pid = await self.create()
        await self.activate(pid)
        self.send.side_effect = TimeoutError()
        due = datetime(2026, 12, 7, 18, tzinfo=MADRID)
        await self.bot.tick(due)
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "uncertain")
        restarted = self.new_bot()
        await restarted.tick(due)
        self.send.assert_awaited_once()
        self.plan(pid)["events"]["pista2"].update(status="sending", attempt="interrupted")
        await restarted.tick(due)
        await restarted.tick(due)
        self.assertEqual(self.plan(pid)["events"]["pista2"]["status"], "uncertain")
        self.assertEqual(self.notify.await_count, 2)

    async def test_timeout_is_ambiguous_and_not_retried(self):
        pid = await self.create()
        await self.activate(pid)
        async def delayed(*args):
            await asyncio.sleep(1)
        self.send.side_effect = delayed
        with patch("vaca_campaigns.SEND_TIMEOUT_SECONDS", 0.001):
            await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "uncertain")
        await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.send.assert_awaited_once()

    async def test_pause_and_cancel_keep_sent_history(self):
        pid = await self.create()
        await self.activate(pid)
        due = datetime(2026, 12, 7, 18, tzinfo=MADRID)
        await self.command("/vaca_pausa on")
        await self.bot.tick(due)
        self.send.assert_not_awaited()
        await self.command("/vaca_pausa off")
        self.global_pause = True
        await self.bot.tick(due)
        self.send.assert_not_awaited()
        self.global_pause = False
        await self.bot.tick(due)
        await self.command(f"/vaca_cancelar {pid}")
        await self.bot.tick(datetime(2026, 12, 10, 8, tzinfo=MADRID))
        self.send.assert_awaited_once()
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "sent")
        self.assertEqual(self.plan(pid)["events"]["manana"]["status"], "cancelled")

    async def test_text_or_time_edit_requires_reactivation(self):
        pid = await self.create()
        await self.activate(pid)
        await self.command(f"/vaca_texto {pid} pista1 | Una pista revisada")
        self.assertEqual(self.plan(pid)["status"], "draft")
        await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.send.assert_not_awaited()
        await self.activate(pid)
        await self.command(f"/vaca_hora {pid} pista1 08/12/2026 19:00")
        self.assertEqual(self.plan(pid)["status"], "draft")
        self.assertEqual(self.plan(pid)["events"]["pista1"]["at"], "2026-12-08T19:00:00+01:00")

    async def test_reschedule_preserves_sent_and_texts_without_replay(self):
        pid = await self.create()
        await self.activate(pid)
        await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.now = datetime(2026, 12, 8, 8, tzinfo=MADRID)
        await self.command(f"/vaca_fecha {pid} 15/12/2026 09:00")
        self.assertEqual(self.plan(pid)["status"], "draft")
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "sent")
        self.assertEqual(self.plan(pid)["events"]["pista2"]["at"], "2026-12-14T18:00:00+01:00")
        self.assertEqual(self.plan(pid)["events"]["pista2"]["text"], MESSAGES["clues"][1])
        await self.activate(pid)
        await self.bot.tick(datetime(2026, 12, 12, 18, tzinfo=MADRID))
        self.send.assert_awaited_once()

    async def test_morning_time_cannot_move_to_another_year_without_rescheduling_clues(self):
        pid = await self.create()
        await self.activate(pid)
        original = copy.deepcopy(self.plan(pid))
        incoming = await self.command(f"/vaca_hora {pid} manana 10/12/2027 08:00")
        self.assertEqual(self.plan(pid), original)
        self.assertIn("/vaca_fecha", incoming.effective_chat.send_message.call_args.args[0])
        await self.command(f"/vaca_fecha {pid} 10/12/2027 08:00")
        self.assertEqual(self.plan(pid)["status"], "draft")
        self.assertTrue(all(event["at"].startswith("2027-12-")
                            for event in self.plan(pid)["events"].values()))

    async def test_cancellation_during_send_does_not_resurrect_plan(self):
        pid = await self.create()
        await self.activate(pid)
        async def cancel_during_send(*args):
            await self.command(f"/vaca_cancelar {pid}")
            # A concurrent scheduler must not classify this in-flight send as a restart.
            await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.send.side_effect = cancel_during_send
        await self.bot.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.assertEqual(self.plan(pid)["status"], "cancelled")
        self.assertEqual(self.plan(pid)["events"]["pista1"]["status"], "sent")
        self.assertEqual(self.plan(pid)["events"]["pista2"]["status"], "cancelled")
        self.send.assert_awaited_once()

    async def test_group_never_receives_secrets(self):
        pid = await self.create()
        incoming = update(f"/vaca_visitas {pid}", chat_type="group")
        await self.bot.handle_admin(incoming, None)
        incoming.effective_chat.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
