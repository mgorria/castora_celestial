"""Owner Centralita transport with real PTB routing and simulated Bot API only."""

import asyncio
import copy
import json
import os
import time
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from aiohttp import ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CallbackQueryHandler, CommandHandler

import main
from test_web_integration import OfflineTelegramRequest
from web_bridge import MAX_EVENTS, RETENTION_SECONDS, WebBridge


TOKEN = "offline-owner-bridge-token-longer-than-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Castori-Actor": "owner", "X-Castori-Owner-Id": "owner-test"}
SANDRA_HEADERS = {**HEADERS, "X-Castori-Actor": "sandra"}


class AdminTelegramRequest(OfflineTelegramRequest):
    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        if endpoint != "editMessageText":
            return await super().do_request(url, method, request_data, **kwargs)
        params = request_data.parameters
        self.calls.append((endpoint, copy.deepcopy(params)))
        result = self.messages[(int(params["chat_id"]), params["message_id"])]
        result["text"] = params["text"]
        result.pop("reply_markup", None)
        if params.get("reply_markup"):
            result["reply_markup"] = params["reply_markup"]
        return 200, json.dumps({"ok": True, "result": result}).encode()


class AdminBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"castori_partner_chat_id": 11, "mimosuga_partner_chat_id": 11}
        self.apps = {}
        self.app = None
        self.transports = []
        self.stack = ExitStack()
        self.provider = AsyncMock(return_value={"system": {"database": False}, "admin_identity_matches": True})
        self.access = AsyncMock()
        self.access.status.return_value = {"configured": True, "unlocked": True, "expires_at": "2099-01-01T00:00:00+00:00"}

        def save(data):
            self.data = copy.deepcopy(data)

        def make_request(**kwargs):
            request = AdminTelegramRequest()
            self.transports.append(request)
            return request

        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), save, lambda: self.apps,
            lambda actor: {"owner": 22, "sandra": 11}.get(actor), token=TOKEN,
            get_admin_app=lambda: self.app, admin_state_provider=self.provider,
            admin_actor_id=lambda: main.admin_chat_id(), admin_access=self.access)
        for key, value in {"web_bridge": self.bridge, "animal_apps": self.apps,
                "load_data": lambda: copy.deepcopy(self.data), "save_data": save,
                "MI_CHAT_ID": "22", "TELEGRAM_ADMIN_ID": "22", "SANDRA_TELEGRAM_ID": "11",
                "salchicher": None, "vaca": None, "vaca_campaigns": None}.items():
            self.stack.enter_context(patch.object(main, key, value))
        self.stack.enter_context(patch.object(main, "require_env", return_value="123456:offline"))
        self.stack.enter_context(patch.object(main, "HTTPXRequest", side_effect=make_request))
        self.stack.enter_context(patch.object(main.database, "db_available", return_value=False))
        self.stack.enter_context(patch.dict(os.environ, {"CASTORI_CHAT_ID": "11", "MIMOSUGA_CHAT_ID": "11"}))
        self.app = main.build_centralita_app()
        self.stack.enter_context(patch.object(main, "centralita_app", self.app))
        await self.app.initialize()
        self.apps["castori"] = main.build_animal_app("castori")
        await self.apps["castori"].initialize()
        self.client = TestClient(TestServer(self.bridge.create_app()), timeout=ClientTimeout(total=4))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.bridge.close()
        await self.client.close()
        await self.app.shutdown()
        for app in self.apps.values():
            await app.shutdown()
        self.stack.close()

    async def finish(self):
        if self.bridge.tasks:
            await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)

    async def action(self, text, request_id="admin001", headers=HEADERS):
        response = await self.client.post("/castori-web/admin-action", headers=headers,
            json={"text": text, "request_id": request_id})
        await self.finish()
        return response

    async def events(self, after="0"):
        response = await self.client.get("/castori-web/admin-events", params={"after": after}, headers=HEADERS)
        self.assertEqual(response.status, 200)
        return await response.json()

    async def callback(self, event, data, request_id="callback001", headers=HEADERS):
        response = await self.client.post("/castori-web/admin-callback", headers=headers,
            json={"event_id": event["id"], "data": data, "request_id": request_id})
        await self.finish()
        return response

    async def test_all_admin_routes_require_owner_before_provider_or_dispatch(self):
        for headers, expected in (({}, 401), (SANDRA_HEADERS, 403)):
            for path in ("admin-state", "admin-events", "admin-auth", "admin-invitation", "admin-owner-invitation"):
                response = await self.client.get(f"/castori-web/{path}", headers=headers)
                self.assertEqual(response.status, expected)
            for path, body in (("admin-action", {"text": "/status", "request_id": "denied001"}),
                    ("admin-callback", {"event_id": 1, "data": "autoreply:1:send", "request_id": "denied002"}),
                    ("admin-invitation", {"action": "create"}),
                    ("admin-owner-invitation", {"action": "create"})):
                response = await self.client.post(f"/castori-web/{path}", headers=headers, json=body)
                self.assertEqual(response.status, expected)
        self.provider.assert_not_awaited()
        self.assertEqual(self.bridge.admin_events, [])
        self.assertTrue(all(endpoint == "getMe" for request in self.transports for endpoint, _ in request.calls))

    async def test_admin_state_is_read_only_and_defends_identity_conflicts(self):
        response = await self.client.get("/castori-web/admin-state", headers=HEADERS)
        state = await response.json()
        self.assertEqual(state["actor"], "owner")
        self.assertIn("mimosuga_pendientes", state["commands"])
        self.assertTrue(state["editorial_admin"]["available"])
        self.assertEqual(self.bridge.admin_events, [])
        with patch.object(main, "TELEGRAM_ADMIN_ID", "33"):
            state = await (await self.client.get("/castori-web/admin-state", headers=HEADERS)).json()
            self.assertFalse(state["editorial_admin"]["available"])
            self.assertNotIn("admin_ultimos", state["commands"])
            self.assertEqual((await self.action("/admin_ultimos")).status, 403)
            event = self.bridge.record_admin(22, "Revisar", message_id=90,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Canon", callback_data="adminstory:1:canon")]]))
            self.assertEqual((await self.callback(event, "adminstory:1:canon")).status, 403)
        self.assertTrue(all(endpoint == "getMe" for request in self.transports for endpoint, _ in request.calls))

    async def test_real_centralita_commands_are_idempotent_and_do_not_rebind(self):
        before = copy.deepcopy(self.data)
        response = await self.action("/pausar_programas")
        self.assertEqual(response.status, 202)
        self.assertTrue(self.data["schedules_paused"])
        events = (await self.events())["events"]
        self.assertEqual(events[0]["role"], "user")
        self.assertTrue(any("pausadas" in e["text"].lower() for e in events))
        duplicate = await self.action("/pausar_programas")
        self.assertTrue((await duplicate.json())["duplicate"])
        self.assertEqual(len((await self.events())["events"]), len(events))
        self.assertEqual((await self.action("/reanudar_programas")).status, 409)
        receipt = await self.client.get("/castori-web/request?request_id=admin001", headers=HEADERS)
        self.assertEqual((await receipt.json())["status"], "processed")
        self.assertEqual((await self.client.get("/castori-web/request?request_id=admin001", headers=SANDRA_HEADERS)).status, 404)
        await self.action("/start", "start001")
        for key, value in before.items():
            self.assertEqual(self.data[key], value)
        self.assertNotIn("Centralita Magica", json.dumps(self.data))

    async def test_action_rejects_arbitrary_identity_commands_and_malformed_body(self):
        for text in ("Hola", "/status@Another_bot", "/unknown", "", "/status" + "x" * 4000):
            response = await self.action(text)
            self.assertIn(response.status, (400, 403))
        response = await self.client.post("/castori-web/admin-action", headers=HEADERS,
            json={"text": "/status", "request_id": "admin001", "chat_id": 11})
        self.assertEqual(response.status, 400)
        self.assertEqual(self.bridge.admin_events, [])

    async def test_send_as_animal_keeps_configured_recipient_with_only_fake_delivery(self):
        response = await self.action("/castori Mensaje de prueba privado", "send0001")
        self.assertEqual(response.status, 202)
        animal_sends = [params for endpoint, params in self.transports[1].calls if endpoint == "sendMessage"]
        self.assertEqual(len(animal_sends), 1)
        self.assertEqual(int(animal_sends[0]["chat_id"]), 11)
        self.assertEqual(animal_sends[0]["text"], "Mensaje de prueba privado")
        self.assertEqual(self.data["castori_partner_chat_id"], 11)
        central_sends = [params for endpoint, params in self.transports[0].calls if endpoint == "sendMessage"]
        self.assertTrue(central_sends)
        self.assertTrue(all(int(params["chat_id"]) == 22 for params in central_sends))
        for headers in (HEADERS, SANDRA_HEADERS):
            response = await self.client.get("/castori-web/events?animal=castori", headers=headers)
            self.assertEqual([event["text"] for event in (await response.json())["events"]],
                             ["Mensaje de prueba privado"])
        duplicate = await self.action("/castori Mensaje de prueba privado", "send0001")
        self.assertTrue((await duplicate.json())["duplicate"])
        self.assertEqual(sum(endpoint == "sendMessage" for endpoint, _ in self.transports[1].calls), 1)

    async def test_admin_notifications_are_owner_only_ephemeral_and_never_animal_history(self):
        await self.app.bot.send_message(22, "REGALO_PRIVADO_AVISO_COMPARTIDO")
        await self.app.bot.send_message(11, "NO_ES_DEL_PROPIETARIO")
        feed = await self.events()
        self.assertEqual([e["text"] for e in feed["events"]], ["REGALO_PRIVADO_AVISO_COMPARTIDO"])
        self.assertNotIn("_chat_id", feed["events"][0])
        self.assertNotIn("REGALO_PRIVADO_AVISO_COMPARTIDO", json.dumps(self.data))
        for animal in ("vaca", "salchicher", "mimosuga"):
            response = await self.client.get(f"/castori-web/events?animal={animal}", headers=HEADERS)
            self.assertEqual((await response.json())["events"], [])
        self.bridge.admin_events[0]["timestamp"] = time.time() - RETENTION_SECONDS - 1
        expired = await self.events(feed["cursor"])
        self.assertTrue(expired["reset"])
        self.assertEqual(expired["events"], [])

    async def test_admin_cursor_reset_for_restart_truncation_and_invalid_queries(self):
        initial = await self.events()
        for index in range(MAX_EVENTS + 1):
            self.bridge.record_admin(22, str(index))
        full = await self.events(initial["cursor"])
        self.assertTrue(full["reset"])
        self.assertEqual(len(full["events"]), MAX_EVENTS)
        self.bridge.admin_boot = "f" * 32
        self.assertTrue((await self.events(full["cursor"]))["reset"])
        for query in ("after=nope", "after=-1", "after=0&after=0", "actor=sandra", "after=1"):
            response = await self.client.get(f"/castori-web/admin-events?{query}", headers=HEADERS)
            self.assertEqual(response.status, 400)

    async def test_real_callback_reply_edit_and_alert_are_mirrored_and_buttons_are_bound(self):
        async def review(update, context):
            await update.callback_query.answer("Revisión terminada", show_alert=True)
            await update.callback_query.edit_message_text("Revisado", reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Terminar", callback_data="autoreply:1:reject")]]))
            await update.callback_query.edit_message_reply_markup(reply_markup=None)
        self.app.add_handler(CallbackQueryHandler(review, pattern=r"^autoreply:"), group=-2)
        message = await self.app.bot.send_message(22, "Pendiente", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Enviar", callback_data="autoreply:1:send")]]))
        before = await self.events()
        event = before["events"][0]
        bad = await self.callback(event, "autoreply:999:send", "badbutton01")
        self.assertEqual(bad.status, 403)
        response = await self.callback(event, "autoreply:1:send")
        self.assertEqual(response.status, 202)
        changed = await self.events(before["cursor"])
        edited = next(e for e in changed["events"] if e["id"] == event["id"])
        self.assertEqual(edited["text"], "Revisado")
        self.assertEqual(edited["buttons"], [])
        self.assertTrue(any(e.get("notice") and e["text"] == "Revisión terminada" for e in changed["events"]))
        self.assertEqual((await self.callback(event, "autoreply:1:send", "oldbutton01")).status, 403)
        self.assertNotIn("answerCallbackQuery", [endpoint for endpoint, _ in self.transports[0].calls])

    async def test_handler_failure_is_uncertain_and_never_retried(self):
        async def fail(update, context):
            raise RuntimeError("offline controlled failure")
        self.app.add_handler(CommandHandler("status", fail), group=-2)
        await self.action("/status")
        receipt = await self.client.get("/castori-web/request?request_id=admin001", headers=HEADERS)
        self.assertEqual((await receipt.json())["status"], "uncertain")
        before = len(self.transports[0].calls)
        repeat = await self.action("/status")
        self.assertEqual((await repeat.json())["status"], "uncertain")
        self.assertEqual(len(self.transports[0].calls), before)

    async def test_pending_draft_reopen_is_scoped_and_sends_only_review_to_owner(self):
        draft = {"id": 7, "animal_key": "mimosuga", "incoming_chat_id": 11, "status": "pending",
                 "incoming_text": "- hola", "proposed_text": "Una respuesta para revisar"}
        with patch.object(main.database, "db_available", return_value=True), \
                patch.object(main.database, "get_auto_reply_draft", AsyncMock(return_value=draft)), \
                patch.object(main.database, "get_pending_auto_reply_drafts", AsyncMock(return_value=[draft])) as listed:
            response = await self.action("/mimosuga_pendientes 7")
            self.assertEqual(response.status, 202)
            listed.assert_not_awaited()
            event = next(e for e in (await self.events())["events"] if e["buttons"])
            self.assertEqual(event["buttons"][0][0]["data"], "autoreply:7:send")
            self.assertEqual(event["buttons"][0][1]["data"], "autoreply:7:reject")
            await self.action("/mimosuga_pendientes", "allpending01")
            listed.assert_awaited_once_with(animal_key="mimosuga", chat_id=11, limit=20)
            draft["incoming_chat_id"] = 99
            await self.action("/mimosuga_pendientes 7", "notours001")
            self.assertIn("No hay respuestas pendientes", (await self.events())["events"][-1]["text"])
        self.assertTrue(all(endpoint == "getMe" for endpoint, _ in self.transports[1].calls))
        central_sends = [p for endpoint, p in self.transports[0].calls if endpoint == "sendMessage"]
        self.assertTrue(all(int(p["chat_id"]) == 22 for p in central_sends))

    async def test_telegram_ingress_is_owner_private_and_synthetic_is_not_duplicated(self):
        for chat_id in (11, 22):
            payload = {"update_id": chat_id, "message": {"message_id": 9, "date": int(time.time()),
                "chat": {"id": chat_id, "type": "private"},
                "from": {"id": chat_id, "is_bot": False, "first_name": "Test"}, "text": "/start",
                "entities": [{"type": "bot_command", "offset": 0, "length": 6}]}}
            await self.app.process_update(Update.de_json(payload, self.app.bot))
        texts = [e["text"] for e in (await self.events())["events"] if e["role"] == "user"]
        self.assertEqual(texts, ["/start"])
        await self.action("/status", "webstatus01")
        self.assertEqual(sum(e["text"] == "/status" for e in (await self.events())["events"]), 1)

    async def test_saved_review_cannot_send_to_a_rebound_recipient(self):
        self.apps["mimosuga"] = main.build_animal_app("mimosuga")
        await self.apps["mimosuga"].initialize()
        draft = {"id": 7, "animal_key": "mimosuga", "incoming_chat_id": 11, "status": "pending",
                 "incoming_text": "- hola", "proposed_text": "Respuesta sólo para la destinataria original"}
        with patch.object(main.database, "db_available", return_value=True), \
                patch.object(main.database, "get_auto_reply_draft", AsyncMock(return_value=draft)), \
                patch.object(main.database, "reserve_auto_reply_draft", AsyncMock(return_value=draft)), \
                patch.object(main.database, "release_auto_reply_draft", AsyncMock()) as release, \
                patch.object(main.database, "mark_auto_reply_draft_sent", AsyncMock()) as sent:
            await self.action("/mimosuga_pendientes 7")
            event = next(e for e in (await self.events())["events"] if e["buttons"])
            with patch.dict(os.environ, {"MIMOSUGA_CHAT_ID": "99"}):
                self.assertEqual((await self.callback(event, "autoreply:7:send")).status, 202)
            release.assert_awaited_once_with(7)
            sent.assert_not_awaited()
            self.assertIn("destinataria", (await self.events())["events"][-1]["text"])
        self.assertTrue(all(endpoint == "getMe" for endpoint, _ in self.transports[-1].calls))


if __name__ == "__main__":
    unittest.main()
