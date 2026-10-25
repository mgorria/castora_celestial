"""Real PTB handlers and Bot API serialization, with all Telegram I/O simulated."""

import asyncio
import copy
import json
import os
import time
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ClientTimeout
from aiohttp.test_utils import TestClient, TestServer
from telegram import Update
from telegram.request import BaseRequest

import main
from salchicher import INACTIVITY_SECONDS, Salchicher
from web_bridge import RETENTION_SECONDS, WebBridge


TOKEN = "offline-integration-bridge-token-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Castori-Actor": "sandra"}
OWNER_HEADERS = {**HEADERS, "X-Castori-Actor": "owner"}


class OfflineTelegramRequest(BaseRequest):
    """Exercise real ExtBot methods rather than mocking away their serialization."""

    def __init__(self):
        self.calls = []
        self.messages = {}
        self.next_id = 100

    @property
    def read_timeout(self):
        return 2

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        params = request_data.parameters if request_data else {}
        self.calls.append((endpoint, copy.deepcopy(params)))
        if endpoint == "getMe":
            result = {"id": 777, "is_bot": True, "first_name": "Salchicher", "username": "OfflineCastori_bot"}
        elif endpoint == "sendMessage":
            self.next_id += 1
            result = {"message_id": self.next_id, "date": int(time.time()), "text": params["text"],
                      "chat": {"id": int(params["chat_id"]), "type": "private"},
                      "from": {"id": 777, "is_bot": True, "first_name": "Salchicher"}}
            if params.get("reply_markup"):
                result["reply_markup"] = params["reply_markup"]
            self.messages[(result["chat"]["id"], result["message_id"])] = copy.deepcopy(result)
        elif endpoint == "editMessageReplyMarkup":
            result = self.messages[(int(params["chat_id"]), params["message_id"])]
            result.pop("reply_markup", None)
            if params.get("reply_markup"):
                result["reply_markup"] = params["reply_markup"]
        elif endpoint in {"sendChatAction", "answerCallbackQuery"}:
            result = True
        else:
            raise AssertionError(f"Unexpected Telegram method: {endpoint}")
        return 200, json.dumps({"ok": True, "result": result}).encode()


class WebIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"castori_partner_chat_id": 11, "mimosuga_partner_chat_id": 11,
                     "salchicher_partner_chat_id": 11}
        self.apps = {}
        self.requests = []
        self.patches = ExitStack()
        self.notify = AsyncMock()

        def save(data):
            self.data = copy.deepcopy(data)

        def request(**kwargs):
            transport = OfflineTelegramRequest()
            self.requests.append(transport)
            return transport

        load = lambda: copy.deepcopy(self.data)
        self.bridge = WebBridge(load, save, lambda: self.apps,
                                lambda actor: {"sandra": 11, "owner": 22}.get(actor), token=TOKEN,
                                get_consultorio=lambda: self.doctor)
        self.doctor = Salchicher(load, save, lambda: {11, 22}, main.salchicher_send, self.notify)
        self.doctor.idle_seconds = 0.001
        values = {"web_bridge": self.bridge, "salchicher": self.doctor, "animal_apps": self.apps,
                  "load_data": load, "save_data": save, "MI_CHAT_ID": "22", "SANDRA_TELEGRAM_ID": "11",
                  "centralita_app": SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))}
        for key, value in values.items():
            self.patches.enter_context(patch.object(main, key, value))
        self.patches.enter_context(patch.object(main, "require_env", return_value="123456:offline"))
        self.patches.enter_context(patch.object(main, "HTTPXRequest", side_effect=request))
        self.patches.enter_context(patch.dict(os.environ, {
            "SALCHICHER_CHAT_ID": "11", "CASTORI_CHAT_ID": "11", "MIMOSUGA_CHAT_ID": "11"}))
        for animal in ("salchicher", "mimosuga"):
            app = main.build_animal_app(animal)
            self.apps[animal] = app
            await app.initialize()
        self.client = TestClient(TestServer(self.bridge.create_app()), timeout=ClientTimeout(total=4))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.bridge.close()
        await self.doctor.close()
        await self.client.close()
        for app in self.apps.values():
            await app.shutdown()
        self.patches.close()

    async def post(self, text, request_id="request001", animal="salchicher", headers=None):
        response = await self.client.post("/castori-web/message", headers=headers or HEADERS,
                                          json={"animal": animal, "text": text, "request_id": request_id})
        if self.bridge.tasks:
            await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)
        return response

    async def consultation_message(self, text, request_id="consult001"):
        active = self.doctor.active_consultation(11)
        response = await self.client.post("/castori-web/consultation-message", headers=HEADERS,
            json={"consultation_id": active["id"], "text": text, "request_id": request_id})
        if self.bridge.tasks:
            await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)
        return response

    async def events(self, actor="sandra", after=0):
        response = await self.client.get(f"/castori-web/events?animal=salchicher&after={after}",
                                         headers={**HEADERS, "X-Castori-Actor": actor})
        self.assertEqual(response.status, 200)
        return await response.json()

    async def telegram(self, text, message_id=1, actor=11):
        message = {"message_id": message_id, "date": int(time.time()),
                   "chat": {"id": actor, "type": "private"},
                   "from": {"id": actor, "first_name": "Patita", "is_bot": False}, "text": text}
        if text.startswith("/"):
            message["entities"] = [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}]
        app = self.apps["salchicher"]
        await app.process_update(Update.de_json({"update_id": message_id, "message": message}, app.bot))

    def seed_consultation(self, actor=11):
        self.doctor.set_session(actor, {"shared": False, "history": [], "asked": [], "version": 1,
                                       "pending": False, "updated_at": time.time()})

    async def test_real_ptb_telegram_ingress_does_not_save_health_text_before_consent(self):
        await self.telegram("SINTOMA_SIN_CONSENTIMIENTO")
        self.assertNotIn("SINTOMA_SIN_CONSENTIMIENTO", json.dumps(self.data))
        self.assertIsNone(self.doctor.session(11))
        events = (await self.events())["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["role"], "assistant")
        self.assertTrue(events[0]["buttons"])
        self.notify.assert_not_awaited()

    async def test_web_ingress_does_not_save_health_text_before_consent(self):
        response = await self.post("SINTOMA_WEB_SIN_CONSENTIMIENTO")
        self.assertEqual(response.status, 409)
        self.assertNotIn("SINTOMA_WEB_SIN_CONSENTIMIENTO", json.dumps(self.data))
        self.assertIsNone(self.doctor.session(11))
        self.assertEqual(len((await self.events())["events"]), 0)
        self.notify.assert_not_awaited()

    async def test_emergency_before_consent_does_not_persist_input_or_notify_owner(self):
        await self.telegram("No puedo respirar SINTOMA_URGENTE_PRIVADO")
        self.assertNotIn("SINTOMA_URGENTE_PRIVADO", json.dumps(self.data))
        events = (await self.events())["events"]
        self.assertEqual(len(events), 1)
        self.assertIn("112", events[0]["text"])
        self.notify.assert_not_awaited()

    async def test_legacy_consent_callback_cannot_skip_explicit_web_consultation(self):
        await self.telegram("/consulta")
        before = await self.events()
        offer = before["events"][0]
        response = await self.client.post("/castori-web/callback", headers=HEADERS, json={
            "animal": "salchicher", "event_id": offer["id"], "data": "salchicher:private", "request_id": "callback001"})
        self.assertEqual(response.status, 403)
        self.assertIsNone(self.doctor.session(11))
        response = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "start", "retain_history": True})
        self.assertEqual(response.status, 200)
        self.assertFalse(self.doctor.session(11)["shared"])
        changed = (await self.events(after=before["cursor"]))["events"]
        self.assertTrue(changed)
        self.assertTrue(all(not e["buttons"] for e in changed))
        self.assertNotIn(offer["id"], [e["id"] for e in changed])
        self.assertNotIn("answerCallbackQuery", [c[0] for c in self.requests[0].calls])
        self.notify.assert_not_awaited()

    async def test_send_chunks_are_mirrored_once_and_visible_in_both_house_views(self):
        self.seed_consultation()
        text = "Primera parte. " * 350 + "\n\n" + "Segunda parte. " * 350
        await main.salchicher_send(11, text)
        actual = (await self.events())["events"]
        self.assertEqual([e["text"] for e in actual], main.split_telegram_text(text))
        self.assertGreater(len(actual), 1)
        self.assertEqual(len({e["message_id"] for e in actual}), len(actual))
        self.assertEqual((await self.events("owner"))["events"], actual)
        self.assertNotIn("22:salchicher", self.data["web_bridge"]["inboxes"])

    async def test_active_input_not_duplicated_and_forget_from_telegram_or_web_purges(self):
        for origin in ("telegram", "web"):
            self.doctor.start_consultation(11, retain_history=True)
            with patch("salchicher.generate_care_reply", AsyncMock(return_value=("RESPUESTA_PRIVADA", []))):
                await self.consultation_message("SINTOMA_CONSENTIDO", request_id=f"message_{origin}")
                await asyncio.wait_for(asyncio.gather(*list(self.doctor.tasks.values())), 3)
            before = await self.events()
            self.assertEqual(sum(e["text"] == "SINTOMA_CONSENTIDO" for e in before["events"]), 1)
            if origin == "telegram":
                await self.telegram("/olvidar", message_id=10)
            else:
                await self.post("/olvidar", request_id="forget_web")
            after = await self.events(after=before["cursor"])
            self.assertTrue(after["reset"])
            self.assertNotIn("SINTOMA_CONSENTIDO", json.dumps(self.data))
            self.assertNotIn("RESPUESTA_PRIVADA", json.dumps(self.data))
            self.assertIsNone(self.doctor.session(11))
        self.notify.assert_not_awaited()

    async def test_expired_session_purges_recent_private_mirror_but_leaves_consent_offer(self):
        await self.telegram("/consulta")
        self.seed_consultation()
        self.bridge.record("salchicher", 11, "SINTOMA_RETENIDO", role="user")
        self.bridge.record("salchicher", 11, "RESPUESTA_RETENIDA")
        session = self.doctor.session(11)
        session["updated_at"] = time.time() - RETENTION_SECONDS - 1
        self.doctor.set_session(11, session)
        self.bridge.maintenance()
        events = (await self.events())["events"]
        self.assertNotIn("SINTOMA_RETENIDO", json.dumps(self.data))
        self.assertNotIn("RESPUESTA_RETENIDA", json.dumps(self.data))
        self.assertEqual(len(events), 1)
        self.assertTrue(events[0]["buttons"])

    async def test_owner_start_cannot_rebind_any_existing_recipient(self):
        before = copy.deepcopy(self.data)
        response = await self.post("/start", headers=OWNER_HEADERS)
        self.assertEqual(response.status, 403)
        response = await self.post("/start", animal="mimosuga", headers=OWNER_HEADERS, request_id="request002")
        self.assertEqual(response.status, 403)
        for key, value in before.items():
            self.assertEqual(self.data[key], value)
        self.assertIsNone(self.doctor.session(22))

    async def test_consultation_archive_is_shared_read_only_and_deleted_for_both(self):
        start = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "start", "retain_history": True})
        item = (await start.json())["consultation"]
        self.assertEqual(item["status"], "active")
        self.assertTrue(item["retained"])
        again = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "start", "retain_history": True})
        self.assertEqual(again.status, 409)
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("CUIDADO_PRIVADO", []))):
            message = await self.consultation_message("SINTOMA_ARCHIVADO")
            self.assertEqual(message.status, 202)
            await asyncio.wait_for(asyncio.gather(*list(self.doctor.tasks.values())), 3)
        listed = await self.client.get("/castori-web/consultations", headers=HEADERS)
        listing = await listed.json()
        self.assertEqual(listing["active_id"], item["id"])
        self.assertNotIn("messages", listing["consultations"][0])
        owner = await self.client.get("/castori-web/consultations", headers=OWNER_HEADERS)
        self.assertEqual((await owner.json())["consultations"], listing["consultations"])
        for action in (None, "close", "delete"):
            if action:
                forbidden = await self.client.post("/castori-web/consultation-action", headers=OWNER_HEADERS,
                    json={"action": action, "consultation_id": item["id"]})
            else:
                forbidden = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=OWNER_HEADERS)
            self.assertEqual(forbidden.status, 403 if action else 200)
            if not action:
                self.assertIn("SINTOMA_ARCHIVADO", str((await forbidden.json())["consultation"]["messages"]))
        close = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "close", "consultation_id": item["id"]})
        closed = (await close.json())["consultation"]
        self.assertEqual(closed["status"], "recovered")
        self.assertEqual(closed["closure_reason"], "feeling_better")
        self.assertIn("SINTOMA_ARCHIVADO", str(closed["messages"]))
        self.assertEqual((await self.events())["events"], [])
        detail = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=HEADERS)
        self.assertEqual(detail.status, 200)
        owner_detail = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=OWNER_HEADERS)
        self.assertEqual(await owner_detail.json(), await detail.json())
        delete = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "delete", "consultation_id": item["id"]})
        self.assertEqual(await delete.json(), {"consultation": None, "deleted": True})
        self.assertNotIn("SINTOMA_ARCHIVADO", json.dumps(self.data))
        self.assertNotIn("CUIDADO_PRIVADO", json.dumps(self.data))
        for headers in (HEADERS, OWNER_HEADERS):
            self.assertEqual((await self.client.get("/castori-web/consultation?id=" + item["id"], headers=headers)).status, 404)
        self.notify.assert_not_awaited()

    async def test_temporary_consultation_close_erases_history_instead_of_archiving(self):
        response = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "start", "retain_history": False})
        item = (await response.json())["consultation"]
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("TEMPORAL_RESPUESTA", []))):
            await self.consultation_message("TEMPORAL_SINTOMA")
            await asyncio.wait_for(asyncio.gather(*list(self.doctor.tasks.values())), 3)
        response = await self.client.post("/castori-web/consultation-action", headers=HEADERS,
            json={"action": "close", "consultation_id": item["id"]})
        self.assertIsNone((await response.json())["consultation"])
        self.assertNotIn("TEMPORAL_", json.dumps(self.data))
        response = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=HEADERS)
        self.assertEqual(response.status, 404)

    async def test_retained_episode_closes_inactive_after_30_days_not_recovered(self):
        item = self.doctor.start_consultation(11, retain_history=True)
        self.bridge.record("salchicher", 11, "CUIDADOS ANTIGUOS")
        with patch("salchicher.time.time", return_value=item["updated_at"] + INACTIVITY_SECONDS + 1):
            response = await self.client.get("/castori-web/consultations", headers=HEADERS)
            listing = await response.json()
            self.assertIsNone(listing["active_id"])
            self.assertEqual(listing["consultations"][0]["status"], "inactive")
            self.assertEqual(listing["consultations"][0]["closure_reason"], "inactivity")
            self.assertEqual(listing["consultations"][0]["updated_at"], item["updated_at"])
            self.assertEqual((await self.events())["events"], [])
            response = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=HEADERS)
            self.assertEqual(response.status, 200)

    async def test_queued_message_cannot_fall_into_a_different_consultation(self):
        old = self.doctor.start_consultation(11, retain_history=True)
        lock = self.bridge.locks.setdefault(11, asyncio.Lock())
        await lock.acquire()
        try:
            response = await self.client.post("/castori-web/consultation-message", headers=HEADERS,
                json={"consultation_id": old["id"], "text": "MENSAJE_TARDIO", "request_id": "stale001"})
            self.assertEqual(response.status, 202)
            self.doctor.close_consultation(11, old["id"])
            new = self.doctor.start_consultation(11, retain_history=True)
        finally:
            lock.release()
        await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)
        response = await self.client.get("/castori-web/request?request_id=stale001", headers=HEADERS)
        self.assertEqual((await response.json())["status"], "rejected")
        self.assertNotIn("MENSAJE_TARDIO", json.dumps(self.data))
        self.assertEqual(self.doctor.active_consultation(11)["id"], new["id"])

    async def test_consultation_routes_require_exact_shapes_and_server_identity(self):
        for body in ({"action": "start"}, {"action": "start", "retain_history": "true"},
                     {"action": "start", "retain_history": True, "chat_id": 22},
                     {"action": "start", "retain_history": True, "shared": True}, {"action": []}):
            response = await self.client.post("/castori-web/consultation-action", headers=HEADERS, json=body)
            self.assertEqual(response.status, 400)
        for path in ("consultations?chat_id=22", "consultation?id=validtest&id=validtest", "consultation?id=validtest&actor=owner"):
            response = await self.client.get("/castori-web/" + path, headers=HEADERS)
            self.assertEqual(response.status, 400)
        self.seed_consultation()
        response = await self.post("No iniciar por el chat")
        self.assertEqual(response.status, 409)
        response = await self.client.post("/castori-web/consultation-message", headers=HEADERS,
            json={"consultation_id": "unknown001", "text": "Sin consulta web", "request_id": "none0010"})
        self.assertEqual(response.status, 409)
        item = self.doctor.start_consultation(11, retain_history=False)
        for extra in ({"actor": "owner"}, {"chat_id": 22}, {"animal": "vaca"}):
            response = await self.client.post("/castori-web/consultation-message", headers=HEADERS,
                json={"consultation_id": item["id"], "text": "No aceptar extras", "request_id": "exact001", **extra})
            self.assertEqual(response.status, 400)
        response = await self.client.post("/castori-web/consultation-message", headers=OWNER_HEADERS,
            json={"consultation_id": item["id"], "text": "No usar la consulta de Sandra", "request_id": "owner001"})
        self.assertEqual(response.status, 403)

    async def test_urgent_notice_survives_temporary_deletion_and_retained_closure(self):
        for retained in (False, True):
            with self.subTest(retained=retained):
                item = self.doctor.start_consultation(11, retain_history=retained)
                request_id = "urgent_saved" if retained else "urgent_temporary"
                body = {"consultation_id": item["id"], "text": "No puedo respirar SINTOMA_URGENCIA",
                        "request_id": request_id}
                response = await self.client.post("/castori-web/consultation-message", headers=HEADERS, json=body)
                self.assertEqual(response.status, 202)
                await asyncio.wait_for(asyncio.gather(*list(self.bridge.tasks)), 3)
                response = await self.client.get("/castori-web/request?request_id=" + request_id, headers=HEADERS)
                self.assertEqual(await response.json(), {
                    "request_id": request_id, "status": "processed", "notice": "urgent_help"})
                receipt = self.data["web_bridge"]["requests"]["11:" + request_id]
                self.assertNotIn("SINTOMA_URGENCIA", json.dumps(receipt))
                duplicate = await self.client.post("/castori-web/consultation-message", headers=HEADERS, json=body)
                self.assertEqual((await duplicate.json())["notice"], "urgent_help")
                self.assertTrue((await duplicate.json())["duplicate"])
                foreign = await self.client.get("/castori-web/request?request_id=" + request_id, headers=OWNER_HEADERS)
                self.assertEqual(foreign.status, 404)
                detail = await self.client.get("/castori-web/consultation?id=" + item["id"], headers=HEADERS)
                if retained:
                    self.assertEqual(detail.status, 200)
                    self.assertEqual((await detail.json())["consultation"]["closure_reason"], "urgent_help")
                else:
                    self.assertEqual(detail.status, 404)
                    self.assertNotIn("SINTOMA_URGENCIA", json.dumps(self.data))
                self.assertIsNone(self.doctor.active_consultation(11))

    async def test_urgent_web_notice_is_available_even_if_telegram_delivery_fails(self):
        self.doctor.start_consultation(11, retain_history=False)
        with patch.object(self.doctor, "send", AsyncMock(side_effect=TimeoutError("offline"))):
            await self.consultation_message("No puedo respirar TEXTO_NO_GUARDAR", request_id="urgent_failed")
        response = await self.client.get("/castori-web/request?request_id=urgent_failed", headers=HEADERS)
        self.assertEqual(await response.json(), {
            "request_id": "urgent_failed", "status": "uncertain", "notice": "urgent_help"})
        self.assertNotIn("TEXTO_NO_GUARDAR", json.dumps(self.data))


if __name__ == "__main__":
    unittest.main()
