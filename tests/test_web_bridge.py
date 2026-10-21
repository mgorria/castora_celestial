"""Bridge tests use local HTTP and fake Telegram applications; no external calls."""

import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update, User
from telegram.ext import ApplicationBuilder, CommandHandler, ExtBot

from web_bridge import MAX_EVENTS, RETENTION_SECONDS, RecordingExtBot, WebBridge


TOKEN = "test-bridge-token-that-is-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Castori-Actor": "sandra"}
OWNER_HEADERS = {**HEADERS, "X-Castori-Actor": "owner"}


class FakeApplication:
    def __init__(self):
        self.bot = SimpleNamespace(id=777, username="CastoriTest_bot")
        self.updates = []
        self.errors = []
        self.callback = None

    def add_error_handler(self, callback):
        self.errors.append(callback)

    async def process_update(self, update):
        self.updates.append(update)
        if self.callback:
            await self.callback(update)


class WebBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {
            "vaca_campaigns": {"secret_gifts": "NO_PUBLICAR"},
            "vaca": {"sessions": {"11": {"wishes": [{"id": "w1", "name": "Libro",
                        "details": "Ilustrado", "favorite": True, "url": "https://example.com/book",
                        "private": "NO_PUBLICAR"}]}, "22": {"wishes": [{"id": "w1", "name": "Prueba dueño"}]}}},
            "salchicher": {"sessions": {"11": {"shared": False, "updated_at": time.time(),
                                                "history": [{"content": "SINTOMA_PRIVADO"}]}}},
        }
        self.apps = {animal: FakeApplication() for animal in ("castori", "mimosuga", "vaca", "salchicher", "corte")}

        def save(data):
            self.data = copy.deepcopy(data)

        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), save, lambda: self.apps,
                                lambda actor: {"sandra": 11, "owner": 22}.get(actor), token=TOKEN)
        self.client = TestClient(TestServer(self.bridge.create_app()), timeout=ClientTimeout(total=5))
        await asyncio.wait_for(self.client.start_server(), 5)

    async def asyncTearDown(self):
        await self.bridge.close()
        await self.client.close()

    async def finish(self):
        if self.bridge.tasks:
            await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)

    async def post(self, path="message", body=None, headers=None):
        return await self.client.post(f"/castori-web/{path}", json=body or {},
                                      headers=HEADERS if headers is None else headers)

    async def get_events(self, animal="mimosuga", after=0, headers=None):
        response = await self.client.get(f"/castori-web/events?animal={animal}&after={after}",
                                         headers=HEADERS if headers is None else headers)
        self.assertEqual(response.status, 200)
        return await response.json()

    def keyboard_event(self, animal="salchicher", chat_id=11, data="salchicher:private"):
        return self.bridge.record(animal, chat_id, "Elige", message_id=99,
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Privada", callback_data=data)]]))

    async def test_health_is_minimal_and_state_requires_bearer(self):
        response = await self.client.get("/castori-web/health")
        self.assertEqual(await response.json(), {"ok": True})
        response = await self.client.get("/castori-web/state")
        self.assertEqual(response.status, 401)
        self.assertEqual(await response.json(), {"error": "unauthorized"})
        response = await self.post(body={"animal": "vaca", "text": "/pedir libro", "request_id": "request001"}, headers={})
        self.assertEqual(response.status, 401)
        self.assertEqual(self.apps["vaca"].updates, [])

    async def test_invalid_actor_and_browser_origin_rejected(self):
        for headers in ({**HEADERS, "X-Castori-Actor": "admin"}, {**HEADERS, "Origin": "https://evil.example"}):
            response = await self.client.get("/castori-web/state", headers=headers)
            self.assertEqual(response.status, 403)

    async def test_state_explicit_projection_and_actor_wishlist(self):
        response = await self.client.get("/castori-web/state", headers=HEADERS)
        state = await response.json()
        self.assertEqual(state["wishes"][0]["name"], "Libro")
        self.assertEqual(state["private_consultation"], {"active": True, "sharing": False})
        self.assertFalse(next(c for c in state["characters"] if c["id"] == "dulcimiel")["available"])
        self.assertNotIn("NO_PUBLICAR", str(state))
        self.assertNotIn("SINTOMA_PRIVADO", str(state))
        response = await self.client.get("/castori-web/state", headers=OWNER_HEADERS)
        state = await response.json()
        self.assertEqual(state["wishes"][0]["name"], "Prueba dueño")
        self.assertFalse(state["private_consultation"]["active"])
        for character in state["characters"]:
            if character["id"] in {"castori", "mimosuga", "corte"}:
                self.assertFalse(character["available"])
                self.assertEqual(character["reason"], "owner_uses_centralita")

    async def test_events_isolate_actors_animals_and_ineligible_ids(self):
        self.bridge.record("salchicher", 11, "Privado Sandra", message_id=1)
        self.bridge.record("salchicher", 22, "Privado propietario", message_id=2)
        self.bridge.record("mimosuga", 11, "Cuento", message_id=3)
        self.assertIsNone(self.bridge.record("salchicher", 33, "Intruso"))
        self.assertEqual([e["text"] for e in (await self.get_events("salchicher"))["events"]], ["Privado Sandra"])
        self.assertEqual([e["text"] for e in (await self.get_events("salchicher", headers=OWNER_HEADERS))["events"]], ["Privado propietario"])
        self.assertEqual([e["text"] for e in (await self.get_events())["events"]], ["Cuento"])

    async def test_dispatch_builds_real_update_and_command_entity(self):
        response = await self.post(body={"animal": "mimosuga", "text": "/cuento una carta", "request_id": "request001"})
        self.assertEqual(response.status, 202)
        await self.finish()
        update = self.apps["mimosuga"].updates[0]
        self.assertIsInstance(update, Update)
        self.assertEqual(update.effective_user.id, 11)
        self.assertEqual(update.effective_chat.id, 11)
        self.assertLess(update.update_id, 0)
        self.assertEqual(update.message.entities[0].type, "bot_command")
        self.assertEqual(update.message.entities[0].length, 7)
        self.assertEqual((await self.get_events())["events"][0]["role"], "user")

    async def test_native_ptb_command_handler_receives_args(self):
        bot = RecordingExtBot(token="123:offline", bridge=self.bridge, animal_key="mimosuga")
        object.__setattr__(bot, "_bot_user", User(777, "Test", True, username="CastoriTest_bot"))
        app = ApplicationBuilder().bot(bot).updater(None).build()
        app._initialized = True
        captured = []

        async def handler(update, context):
            captured.append((update.effective_user.id, context.args))

        app.add_handler(CommandHandler("cuento", handler))
        self.apps["mimosuga"] = app
        await self.post(body={"animal": "mimosuga", "text": "/cuento una carta", "request_id": "request001"})
        await self.finish()
        self.assertEqual(captured, [(11, ["una", "carta"])])

    async def test_admin_commands_and_identity_injection_rejected_before_handler(self):
        for text in ("/status", "/vaca_visita secreto", "/programar mimosuga lunes 10:00 hola", "/start@Other_bot"):
            response = await self.post(body={"animal": "vaca", "text": text, "request_id": "request001"})
            self.assertEqual(response.status, 403)
        response = await self.post(body={"animal": "vaca", "text": "hola", "request_id": "request001", "chat_id": 22})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.apps["vaca"].updates, [])

    async def test_owner_cannot_rebind_legacy_partner_through_start(self):
        for animal in ("castori", "mimosuga", "corte"):
            response = await self.post(body={"animal": animal, "text": "/start", "request_id": "request001"}, headers=OWNER_HEADERS)
            self.assertEqual(response.status, 403)
            self.assertEqual(self.apps[animal].updates, [])

    async def test_duplicate_request_runs_once_and_conflict_rejected(self):
        body = {"animal": "vaca", "text": "/pedir libro", "request_id": "request001"}
        first = await self.post(body=body)
        second = await self.post(body=body)
        self.assertEqual(first.status, 202)
        self.assertTrue((await second.json())["duplicate"])
        await self.finish()
        self.assertEqual(len(self.apps["vaca"].updates), 1)
        third = await self.post(body={**body, "text": "/pedir otro libro"})
        self.assertEqual(third.status, 409)
        status = await self.client.get("/castori-web/request?request_id=request001", headers=HEADERS)
        self.assertEqual((await status.json())["status"], "processed")
        status = await self.client.get("/castori-web/request?request_id=request001", headers=OWNER_HEADERS)
        self.assertEqual(status.status, 404)

    async def test_exception_and_ptb_error_handler_mark_uncertain_without_retry(self):
        async def fail(update):
            raise TimeoutError("PRIVATE_CONTENT_MUST_NOT_APPEAR")

        self.apps["vaca"].callback = fail
        body = {"animal": "vaca", "text": "/pedir libro", "request_id": "request001"}
        await self.post(body=body)
        await self.finish()
        duplicate = await self.post(body=body)
        self.assertEqual((await duplicate.json())["status"], "uncertain")
        self.assertEqual(len(self.apps["vaca"].updates), 1)

        async def swallowed(update):
            for handler in self.apps["mimosuga"].errors:
                await handler(update, SimpleNamespace(error=ValueError()))

        self.apps["mimosuga"].callback = swallowed
        await self.post(body={"animal": "mimosuga", "text": "hola", "request_id": "request002"})
        await self.finish()
        status = await self.client.get("/castori-web/request?request_id=request002", headers=HEADERS)
        self.assertEqual((await status.json())["status"], "uncertain")

    async def test_callback_requires_same_actor_current_button_and_allowed_prefix(self):
        event = self.keyboard_event()
        body = {"animal": "salchicher", "event_id": event["id"], "data": "salchicher:private", "request_id": "request001"}
        for mutation, headers in (({"data": "salchicher:shared"}, HEADERS), ({}, OWNER_HEADERS),
                                  ({"data": "autoreply:99:send"}, HEADERS), ({"animal": "mimosuga"}, HEADERS)):
            response = await self.post("callback", {**body, **mutation}, headers)
            self.assertEqual(response.status, 403)
        response = await self.post("callback", body)
        self.assertEqual(response.status, 202)
        await self.finish()
        update = self.apps["salchicher"].updates[0]
        self.assertEqual(update.callback_query.data, "salchicher:private")
        self.assertEqual(update.callback_query.message.message_id, 99)
        self.assertTrue(update.callback_query.id.startswith("web:"))

    async def test_callback_duplicate_still_succeeds_after_button_removal(self):
        event = self.keyboard_event()
        body = {"animal": "salchicher", "event_id": event["id"], "data": "salchicher:private", "request_id": "request001"}
        await self.post("callback", body)
        await self.finish()
        self.bridge.edit_keyboard("salchicher", 11, 99, None)
        response = await self.post("callback", body)
        self.assertTrue((await response.json())["duplicate"])
        response = await self.post("callback", {**body, "request_id": "request002"})
        self.assertEqual(response.status, 403)

    async def test_owner_cannot_invoke_legacy_callback_even_with_own_recorded_button(self):
        event = self.keyboard_event("corte", 22, "courtdef:1:admin:deny")
        response = await self.post("callback", {"animal": "corte", "event_id": event["id"],
                                  "data": "courtdef:1:admin:deny", "request_id": "request001"}, OWNER_HEADERS)
        self.assertEqual(response.status, 403)
        self.assertEqual(self.apps["corte"].updates, [])

    async def test_restart_marks_pending_uncertain_and_starts_retention_task(self):
        self.data["web_bridge"] = {"sequence": 0, "inboxes": {}, "requests": {
            "11:request001": {"fingerprint": "test", "status": "pending", "at": time.time()}}}
        await self.bridge.start(port=0)
        self.assertEqual(self.data["web_bridge"]["requests"]["11:request001"]["status"], "uncertain")
        self.assertIsNotNone(self.bridge.maintenance_task)
        self.assertFalse(self.bridge.maintenance_task.done())
        self.assertEqual(self.apps["mimosuga"].updates, [])
        await self.bridge.close()
        self.assertIsNone(self.bridge.maintenance_task)

    async def test_edited_keyboard_reappears_with_stable_event_id_and_new_cursor(self):
        event = self.keyboard_event()
        before = await self.get_events("salchicher")
        self.bridge.edit_keyboard("salchicher", 11, 99, None)
        after = await self.get_events("salchicher", before["cursor"])
        self.assertEqual(after["events"][0]["id"], event["id"])
        self.assertEqual(after["events"][0]["buttons"], [])
        self.assertGreater(after["cursor"], before["cursor"])

    async def test_forget_erases_only_selected_actor_and_not_wishes(self):
        self.bridge.record("salchicher", 11, "Privado Sandra", message_id=1)
        self.bridge.record("salchicher", 22, "Privado propietario", message_id=2)
        before = await self.get_events("salchicher")
        await self.post(body={"animal": "salchicher", "text": "/olvidar", "request_id": "request001"})
        await self.finish()
        after = await self.get_events("salchicher", before["cursor"])
        self.assertTrue(after["reset"])
        self.assertEqual(after["events"], [])
        self.assertEqual(len((await self.get_events("salchicher", headers=OWNER_HEADERS))["events"]), 1)
        self.assertEqual(self.data["vaca"]["sessions"]["11"]["wishes"][0]["name"], "Libro")

    async def test_private_events_expire_at_48_hours_and_invalidate_callbacks(self):
        with patch("web_bridge.time.time", return_value=time.time() - RETENTION_SECONDS - 1):
            event = self.keyboard_event()
        events = await self.get_events("salchicher")
        self.assertTrue(events["reset"])
        self.assertEqual(events["events"], [])
        response = await self.post("callback", {"animal": "salchicher", "event_id": event["id"],
                                                "data": "salchicher:private", "request_id": "request001"})
        self.assertEqual(response.status, 403)

    async def test_recording_is_bounded_and_deduplicates_telegram_messages(self):
        for number in range(MAX_EVENTS + 3):
            self.bridge.record("castori", 11, str(number), message_id=number)
        self.bridge.record("castori", 11, "duplicate", message_id=MAX_EVENTS + 2)
        events = (await self.get_events("castori"))["events"]
        self.assertEqual(len(events), MAX_EVENTS)
        self.assertEqual(events[0]["text"], "3")
        self.assertNotIn("duplicate", [event["text"] for event in events])

    async def test_incoming_helper_skips_web_and_erases_telegram_forget(self):
        self.bridge.record("salchicher", 11, "Privado", message_id=1)
        payload = {"update_id": 100, "message": {"message_id": 2, "date": int(time.time()),
                   "chat": {"id": 11, "type": "private"},
                   "from": {"id": 11, "first_name": "Patita", "is_bot": False}, "text": "/olvidar"}}
        self.bridge.record_telegram_update("salchicher", Update.de_json(payload, None))
        self.assertEqual((await self.get_events("salchicher"))["events"], [])
        payload["update_id"] = -100
        payload["message"]["text"] = "No duplicar"
        self.bridge.record_telegram_update("salchicher", Update.de_json(payload, None))
        self.assertEqual((await self.get_events("salchicher"))["events"], [])

    async def test_recording_bot_preserves_delivery_and_only_skips_web_callback_ack(self):
        bot = RecordingExtBot(token="123:offline", bridge=self.bridge, animal_key="salchicher")
        delivered = Message.de_json({"message_id": 99, "date": int(time.time()), "text": "Hola",
                                     "chat": {"id": 11, "type": "private"}}, bot)
        with patch.object(ExtBot, "send_message", AsyncMock(return_value=delivered)) as send:
            self.assertIs(await bot.send_message(11, "Hola"), delivered)
            send.assert_awaited_once_with(11, "Hola")
        self.assertEqual((await self.get_events("salchicher"))["events"][0]["text"], "Hola")
        with patch.object(ExtBot, "answer_callback_query", AsyncMock(return_value=True)) as answer:
            await bot.answer_callback_query("web:abc")
            answer.assert_not_awaited()
            await bot.answer_callback_query("telegram-real-id")
            answer.assert_awaited_once_with("telegram-real-id")

    async def test_recording_failure_cannot_repeat_successful_telegram_delivery(self):
        bot = RecordingExtBot(token="123:offline", bridge=self.bridge, animal_key="salchicher")
        delivered = Message.de_json({"message_id": 99, "date": int(time.time()), "text": "Hola",
                                     "chat": {"id": 11, "type": "private"}}, bot)
        with patch.object(ExtBot, "send_message", AsyncMock(return_value=delivered)) as send:
            with patch.object(self.bridge, "record", side_effect=OSError("disk full")):
                self.assertIs(await bot.send_message(11, "Hola"), delivered)
            send.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
