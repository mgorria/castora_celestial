"""Monday greetings exercise native handlers with synthetic state and no network."""

import __future__
import ast
import asyncio
import copy
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
import uuid
from zoneinfo import ZoneInfo


MADRID = ZoneInfo("Europe/Madrid")
MONDAY = datetime(2026, 10, 26, 6, 0, tzinfo=MADRID)
GREETING = "Buenos días, Patita. Hoy tengo un libro y un abrazo guardados para ti."


def weekly(**values):
    return {"id": "monday01", "kind": "weekly", "animal_key": "mimosuga",
            "weekday": 0, "time": "06:00", "text": "Saludo cariñoso de Mimosuga",
            "generator": "mimosuga_monday", "delivery": "office", "last_sent_date": None,
            "greeting_history": [], **values}


class PortalBot:
    def __init__(self):
        self.send_message = AsyncMock()
        self.send_chat_action = AsyncMock()
        self.send_notification = AsyncMock()
        self._portal_delivery = Mock(return_value=True)


class Runtime:
    """Compile handler dependencies, never module-level deployment configuration."""

    def __init__(self, schedules=(), *, now=MONDAY):
        self.rows = copy.deepcopy(list(schedules))
        self.saves = []
        self.bot = PortalBot()
        self.chat = SimpleNamespace(id=22, type="private", send_message=AsyncMock())
        self.update = SimpleNamespace(effective_chat=self.chat, effective_user=SimpleNamespace(id=22),
                                      message=SimpleNamespace(text=""))
        self.now = now

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None):
                return now.astimezone(tz) if tz else now.replace(tzinfo=None)

        def save(rows):
            self.rows = copy.deepcopy(rows)
            self.saves.append(copy.deepcopy(rows))

        self.ns = {
            "datetime": Clock, "date": date, "timedelta": timedelta, "uuid": uuid, "re": re,
            "APP_TIMEZONE": MADRID, "SCHEDULER_POLL_SECONDS": 30, "logger": Mock(),
            "WEEKDAYS": {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3,
                         "viernes": 4, "sabado": 5, "domingo": 6},
            "WEEKDAY_NAMES": {0: "lunes", 1: "martes", 2: "miercoles", 3: "jueves",
                              4: "viernes", 5: "sabado", 6: "domingo"},
            "ANIMALS": {"mimosuga": {"display_name": "Mimosuga"}},
            "get_schedules": Mock(side_effect=lambda: copy.deepcopy(self.rows)),
            "save_schedules": Mock(side_effect=save), "schedules_paused": Mock(return_value=False),
            "get_partner_chat_id": Mock(return_value=11), "owner_chat_id": Mock(return_value=22),
            "resolve_web_actor": Mock(side_effect=lambda actor: {"sandra": 11, "owner": 22}.get(actor)),
            "is_owner": Mock(return_value=True), "is_private_owner": Mock(return_value=True),
            "has_out_of_character_language": Mock(return_value=False), "append_history": Mock(),
            "generate_monday_greeting": AsyncMock(return_value=GREETING),
            "animal_apps": {"mimosuga": SimpleNamespace(bot=self.bot)},
            "RecordingExtBot": PortalBot,
            "web_bridge": SimpleNamespace(portal=SimpleNamespace(origin="https://house.example")),
            "os": SimpleNamespace(getenv=lambda key, default=None: "true" if key == "CASTORI_WEB_ONLY_DELIVERY" else default),
            "ChatAction": SimpleNamespace(TYPING="typing"), "centralita_app": None,
            "salchicher": None, "vaca": None, "vaca_campaigns": None, "unread_notifier": None,
            "asyncio": asyncio,
        }
        source = Path(__file__).resolve().parents[1] / "main.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        functions = {node.name: node for node in tree.body
                     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        pending = ["central_schedule_mimosuga", "send_scheduled_message", "scheduler_loop",
                   "mark_schedule_before_send", "mark_schedule_after_send"]
        selected = {}
        while pending:
            name = pending.pop()
            if name in selected:
                continue
            function = functions[name]
            selected[name] = function
            pending.extend(node.id for node in ast.walk(function) if isinstance(node, ast.Name)
                           and node.id in functions and node.id not in self.ns and node.id not in selected)
        exec(compile(ast.Module(body=list(selected.values()), type_ignores=[]), str(source), "exec",
                     flags=__future__.annotations.compiler_flag), self.ns)

    async def create(self, args=None):
        await self.ns["central_schedule_mimosuga"](
            self.update, SimpleNamespace(args=["lunes", "06:00"] if args is None else args))

    async def tick(self):
        self.ns["asyncio"] = SimpleNamespace(sleep=AsyncMock(side_effect=asyncio.CancelledError))
        with self.assert_cancelled():
            await self.ns["scheduler_loop"]()

    @staticmethod
    def assert_cancelled():
        return unittest.TestCase().assertRaises(asyncio.CancelledError)


class MondayScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def test_creating_schedule_does_not_generate_or_deliver_early(self):
        runtime = Runtime(now=MONDAY - timedelta(days=1))
        await runtime.create()
        self.assertEqual(len(runtime.rows), 1)
        row = runtime.rows[0]
        self.assertEqual((row["kind"], row["animal_key"], row["generator"], row["weekday"], row["time"]),
                         ("weekly", "mimosuga", "mimosuga_monday", 0, "06:00"))
        self.assertEqual(row["delivery"], "office")
        self.assertIsNone(row["last_sent_date"])
        runtime.ns["generate_monday_greeting"].assert_not_awaited()
        runtime.bot.send_message.assert_not_awaited()

    async def test_identical_dynamic_slot_is_reused_without_second_schedule(self):
        existing = weekly(greeting_history=["Un saludo anterior"])
        runtime = Runtime([existing], now=MONDAY - timedelta(days=1))
        await runtime.create()
        self.assertEqual(runtime.rows, [existing])
        self.assertEqual(runtime.saves, [])
        runtime.bot.send_message.assert_not_awaited()

    async def test_static_mimosuga_at_same_slot_is_preserved_as_a_conflict(self):
        existing = weekly(text="Mensaje fijo existente")
        del existing["generator"]
        runtime = Runtime([existing])
        await runtime.create()
        self.assertEqual(runtime.rows, [existing])
        self.assertEqual(runtime.saves, [])
        runtime.bot.send_message.assert_not_awaited()

    async def test_invalid_or_unauthorized_commands_do_not_modify_schedules(self):
        for args in ([], ["lunes"], ["lunes", "25:00"], ["dia-inexistente", "06:00"]):
            with self.subTest(args=args):
                runtime = Runtime()
                await runtime.create(args)
                self.assertEqual(runtime.rows, [])
        runtime = Runtime()
        runtime.ns["is_owner"].return_value = False
        runtime.ns["is_private_owner"].return_value = False
        await runtime.create()
        self.assertEqual(runtime.rows, [])

    async def test_monday_creation_after_time_waits_for_next_week(self):
        runtime = Runtime(now=MONDAY + timedelta(hours=1))
        await runtime.create()
        self.assertEqual(runtime.rows[0]["last_sent_date"], "2026-10-26")
        runtime.ns["send_scheduled_message"] = AsyncMock(return_value=True)
        await runtime.tick()
        runtime.ns["send_scheduled_message"].assert_not_awaited()

    async def test_invalid_or_owner_portal_identity_is_rejected_before_creation_and_generation(self):
        for recipient in (None, 0, -11, True, 22):
            with self.subTest(recipient=recipient):
                runtime = Runtime()
                runtime.ns["resolve_web_actor"].side_effect = lambda actor: recipient if actor == "sandra" else 22
                await runtime.create()
                self.assertEqual(runtime.rows, [])
                self.assertFalse(await runtime.ns["send_scheduled_message"](weekly()))
                runtime.ns["generate_monday_greeting"].assert_not_awaited()
                runtime.bot.send_message.assert_not_awaited()

    async def test_legacy_telegram_link_never_retargets_or_blocks_a_portal_greeting(self):
        for legacy_partner in (None, 22, 33):
            with self.subTest(legacy_partner=legacy_partner):
                runtime = Runtime(now=MONDAY - timedelta(days=1))
                runtime.ns["get_partner_chat_id"].return_value = legacy_partner
                await runtime.create()
                self.assertEqual(len(runtime.rows), 1)
                runtime.bot.send_message.assert_not_awaited()
                self.assertTrue(await runtime.ns["send_scheduled_message"](copy.deepcopy(runtime.rows[0])))
                runtime.bot.send_message.assert_awaited_once_with(chat_id=11, text=GREETING)
                runtime.ns["get_partner_chat_id"].assert_not_called()
                self.assertEqual(runtime.ns["get_partner_chat_id"].return_value, legacy_partner)

    async def test_static_schedule_keeps_its_existing_telegram_link_and_never_generates(self):
        original = weekly(text="Mensaje fijo existente")
        del original["generator"]
        runtime = Runtime([original])
        runtime.ns["get_partner_chat_id"].return_value = 33
        self.assertTrue(await runtime.ns["send_scheduled_message"](copy.deepcopy(original)))
        runtime.bot.send_message.assert_awaited_once_with(chat_id=33, text=original["text"])
        runtime.ns["get_partner_chat_id"].assert_called_once_with("mimosuga")
        runtime.ns["generate_monday_greeting"].assert_not_awaited()
        self.assertEqual(runtime.rows, [original])

    async def test_an_unavailable_office_never_falls_back_to_telegram(self):
        for change in ("no_bridge", "no_portal", "telegram_mode", "no_bot", "no_recipient"):
            with self.subTest(change=change):
                runtime = Runtime([weekly()])
                if change == "no_bridge":
                    runtime.ns["web_bridge"] = None
                elif change == "no_portal":
                    runtime.ns["web_bridge"].portal = None
                elif change == "telegram_mode":
                    runtime.ns["os"].getenv = lambda key, default=None: "false"
                elif change == "no_bot":
                    runtime.ns["animal_apps"] = {}
                else:
                    runtime.ns["resolve_web_actor"].side_effect = lambda actor: 22 if actor == "owner" else None
                self.assertFalse(await runtime.ns["send_scheduled_message"](weekly()))
                runtime.ns["generate_monday_greeting"].assert_not_awaited()
                runtime.bot.send_message.assert_not_awaited()
                runtime.bot.send_notification.assert_not_awaited()

    async def test_creation_while_paused_never_reactivates_other_programs(self):
        runtime = Runtime()
        runtime.ns["schedules_paused"].return_value = True
        await runtime.create()
        self.assertEqual(runtime.rows, [])
        self.assertEqual(runtime.saves, [])
        self.assertTrue(runtime.ns["schedules_paused"]())
        self.assertFalse(await runtime.ns["send_scheduled_message"](weekly()))
        runtime.ns["generate_monday_greeting"].assert_not_awaited()

    async def test_greeting_uses_madrid_date_and_only_its_previous_greetings(self):
        previous = [f"Saludo anterior {index}" for index in range(10)]
        original = weekly(greeting_history=previous)
        unrelated = weekly(id="other001", time="08:00", greeting_history=["Otro programa"])
        runtime = Runtime([original, unrelated])
        owner_bot = SimpleNamespace(send_message=AsyncMock())
        runtime.ns["centralita_app"] = SimpleNamespace(bot=owner_bot)
        delivered = False

        async def delivery(**kwargs):
            nonlocal delivered
            self.assertEqual(runtime.rows[0]["greeting_history"], previous)
            self.assertEqual(kwargs, {"chat_id": 11, "text": GREETING})
            delivered = True

        runtime.bot.send_message.side_effect = delivery
        self.assertTrue(await runtime.ns["send_scheduled_message"](copy.deepcopy(original)))
        self.assertTrue(delivered)
        runtime.ns["generate_monday_greeting"].assert_awaited_once_with(
            on_date=date(2026, 10, 26), recent_messages=previous[-8:])
        self.assertEqual(runtime.rows[0]["greeting_history"], previous[-7:] + [GREETING])
        self.assertEqual(runtime.rows[1], unrelated)
        runtime.bot.send_notification.assert_not_awaited()
        owner_bot.send_message.assert_not_awaited()

    async def test_cancellation_pause_or_recipient_change_during_generation_prevents_delivery(self):
        for change in ("cancel", "pause", "recipient", "no_portal", "telegram_mode"):
            with self.subTest(change=change):
                original = weekly(greeting_history=["Saludo entregado antes"])
                runtime = Runtime([original])

                async def generate(**kwargs):
                    if change == "cancel":
                        runtime.rows = []
                    elif change == "pause":
                        runtime.ns["schedules_paused"].return_value = True
                    elif change == "recipient":
                        runtime.ns["resolve_web_actor"].side_effect = lambda actor: 33 if actor == "sandra" else 22
                    elif change == "no_portal":
                        runtime.ns["web_bridge"].portal = None
                    else:
                        runtime.ns["os"].getenv = lambda key, default=None: "false"
                    return GREETING

                runtime.ns["generate_monday_greeting"].side_effect = generate
                self.assertFalse(await runtime.ns["send_scheduled_message"](copy.deepcopy(original)))
                runtime.bot.send_message.assert_not_awaited()
                runtime.ns["append_history"].assert_not_called()
                self.assertEqual(runtime.rows, [] if change == "cancel" else [original])

    async def test_history_failure_after_delivery_does_not_turn_success_into_a_retry(self):
        runtime = Runtime([weekly()])
        runtime.ns["remember_mimosuga_greeting"] = Mock(side_effect=OSError("synthetic storage failure"))
        self.assertTrue(await runtime.ns["send_scheduled_message"](weekly()))
        runtime.bot.send_message.assert_awaited_once()

    async def test_failed_delivery_does_not_append_generated_text_to_recent_greetings(self):
        original = weekly(greeting_history=["Saludo ya entregado"])
        runtime = Runtime([original])
        runtime.bot.send_message.side_effect = TimeoutError("synthetic ambiguous delivery")
        try:
            result = await runtime.ns["send_scheduled_message"](copy.deepcopy(original))
        except TimeoutError:
            pass
        else:
            self.assertFalse(result)
        self.assertEqual(runtime.rows, [original])
        runtime.ns["append_history"].assert_not_called()

    async def test_scheduler_only_runs_due_monday_and_respects_pause(self):
        for when, paused in ((MONDAY - timedelta(minutes=1), False),
                             (MONDAY + timedelta(days=1), False), (MONDAY, True)):
            with self.subTest(when=when, paused=paused):
                runtime = Runtime([weekly()], now=when)
                runtime.ns["schedules_paused"].return_value = paused
                runtime.ns["send_scheduled_message"] = AsyncMock(return_value=True)
                await runtime.tick()
                runtime.ns["send_scheduled_message"].assert_not_awaited()
                self.assertIsNone(runtime.rows[0]["last_sent_date"])

    async def test_six_am_stays_in_madrid_in_summer_and_winter(self):
        for instant, expected in (
            (datetime(2026, 7, 6, 3, 59, tzinfo=timezone.utc), 0),
            (datetime(2026, 7, 6, 4, 0, tzinfo=timezone.utc), 1),
            (datetime(2026, 10, 26, 4, 59, tzinfo=timezone.utc), 0),
            (datetime(2026, 10, 26, 5, 0, tzinfo=timezone.utc), 1),
        ):
            with self.subTest(instant=instant):
                runtime = Runtime([weekly()], now=instant)
                runtime.ns["send_scheduled_message"] = AsyncMock(return_value=True)
                await runtime.tick()
                self.assertEqual(runtime.ns["send_scheduled_message"].await_count, expected)

    async def test_due_slot_is_reserved_before_delivery_and_not_replayed_after_restart(self):
        runtime = Runtime([weekly()])

        async def delivery(row):
            self.assertEqual(runtime.rows[0]["last_sent_date"], "2026-10-26")
            self.assertEqual(row["last_sent_date"], "2026-10-26")
            raise TimeoutError("synthetic ambiguous delivery")

        runtime.ns["send_scheduled_message"] = AsyncMock(side_effect=delivery)
        await runtime.tick()
        runtime.ns["send_scheduled_message"].assert_awaited_once()
        restarted = Runtime(runtime.rows, now=MONDAY + timedelta(minutes=1))
        restarted.ns["send_scheduled_message"] = AsyncMock(return_value=True)
        await restarted.tick()
        restarted.ns["send_scheduled_message"].assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
