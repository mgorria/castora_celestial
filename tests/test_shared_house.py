"""Shared-house authorization through HTTP; all accounts and transports are offline."""

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import ClientTimeout
from aiohttp.test_utils import TestClient, TestServer

from portal import COOKIE
from test_web_bridge import FakeApplication
from web_bridge import WebBridge


TOKEN = "shared-house-offline-token-longer-than-32-characters"
ORIGIN = "https://house.example"
OWNER = {"Authorization": "Bearer " + TOKEN, "X-Castori-Actor": "owner",
         "X-Castori-Owner-Id": "owner-test"}
SANDRA = {**OWNER, "X-Castori-Actor": "sandra"}


class SharedHouseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"vaca": {"sessions": {
            "11": {"wishes": [{"id": "sandra-wish", "name": "Libro compartido"}]},
            "22": {"wishes": [{"id": "owner-wish", "name": "Prueba de Telegram del dueño"}]}}}}
        self.identities = {"sandra": 11, "owner": 22}
        self.apps = {name: FakeApplication() for name in ("castori", "mimosuga", "vaca", "salchicher", "corte")}
        self.provider = SimpleNamespace(
            page=AsyncMock(return_value={"messages": [{"text": "Historia de Sandra"}], "archive_available": True}),
            stories=AsyncMock(return_value={"stories": [{"id": 7, "title": "Su cuento"}]}),
            story=AsyncMock(return_value={"story": {"id": 7, "full_text": "Cuento completo"}}),
            record_event=AsyncMock(return_value=True), forget=AsyncMock(return_value=True))
        self.state_provider = AsyncMock(return_value={"source": "shared-house"})
        self.admin_provider = AsyncMock(return_value={"system": {"database": True}})
        self.access = SimpleNamespace(status=AsyncMock(return_value={
            "configured": True, "unlocked": False, "expires_at": None}))
        self.sessions = {name: {"actor": name, "chat_id": chat, "username": name,
                              "expires_at": "2099-01-01T00:00:00+00:00"}
                         for name, chat in self.identities.items()}
        self.accounts = SimpleNamespace(get_session=AsyncMock(side_effect=lambda token: self.sessions.get(token)))

        def save(data):
            self.data = copy.deepcopy(data)

        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), save, lambda: self.apps,
            self.identities.get, token=TOKEN, history_provider=self.provider,
            state_provider=self.state_provider, get_admin_app=lambda: SimpleNamespace(),
            admin_state_provider=self.admin_provider, admin_actor_id=lambda: 22,
            admin_access=self.access, account_service=self.accounts, portal_origin=ORIGIN)
        self.client = TestClient(TestServer(self.bridge.create_app()), timeout=ClientTimeout(total=4))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.bridge.close()
        await self.client.close()

    async def get(self, path, headers=OWNER, prefix="/castori-web/"):
        return await self.client.get(prefix + path, headers=headers)

    async def test_owner_reads_sandra_house_but_not_owners_telegram_test_data(self):
        self.bridge.record("mimosuga", 11, "Cuento para Sandra", message_id=1)
        self.bridge.record("mimosuga", 22, "Ensayo privado del dueño", message_id=2)
        owner = await (await self.get("state")).json()
        sandra = await (await self.get("state", SANDRA)).json()
        self.assertEqual(owner["actor"], "owner")
        self.assertTrue(owner["read_only"])
        self.assertFalse(sandra["read_only"])
        self.assertEqual(owner["wishes"], sandra["wishes"])
        self.assertEqual(owner["wishes"][0]["id"], "sandra-wish")
        self.assertTrue(all(call.args == ("sandra", 11) for call in self.state_provider.await_args_list))
        for headers in (OWNER, SANDRA):
            events = await (await self.get("events?animal=mimosuga", headers)).json()
            self.assertEqual([event["text"] for event in events["events"]], ["Cuento para Sandra"])
            self.assertEqual((await self.get("history?animal=mimosuga&limit=9", headers)).status, 200)
            self.assertEqual((await self.get("stories?limit=4", headers)).status, 200)
            self.assertEqual((await self.get("story?id=7", headers)).status, 200)
        for call in self.provider.page.await_args_list:
            self.assertEqual(call.args, ("sandra", 11, "mimosuga"))
        for provider in (self.provider.stories, self.provider.story):
            self.assertTrue(all(call.args[:2] == ("sandra", 11) for call in provider.await_args_list))

    async def test_owner_normal_writes_are_denied_before_state_or_dispatch_changes(self):
        original = copy.deepcopy(self.data)
        bodies = [("message", {"animal": animal, "text": "/start", "request_id": "ownerwrite"})
                  for animal in self.apps]
        bodies += [
            ("callback", {"animal": "mimosuga", "event_id": 1, "data": "cuento:7:continue", "request_id": "ownercallback"}),
            ("consultation-action", {"action": "start", "retain_history": True}),
            ("consultation-action", {"action": "delete", "consultation_id": "knownconsultation"}),
            ("consultation-message", {"consultation_id": "knownconsultation", "text": "No escribir por Sandra", "request_id": "ownerconsult"}),
        ]
        for prefix, headers in (("/castori-web/", OWNER),
                ("/api/bridge/", {"Cookie": COOKIE + "=owner", "Origin": ORIGIN})):
            for route, body in bodies:
                with self.subTest(prefix=prefix, route=route, body=body):
                    response = await self.client.post(prefix + route, headers=headers, json=body)
                    self.assertEqual(response.status, 403)
                    self.assertEqual(await response.json(), {"error": "read_only"})
        self.assertEqual(self.data, original)
        self.assertFalse(self.bridge.tasks)
        self.assertTrue(all(not app.updates for app in self.apps.values()))

    async def test_no_query_or_header_can_select_arbitrary_house_identity(self):
        self.bridge.record("vaca", 11, "Deseo de Sandra")
        self.bridge.record("vaca", 22, "No debe aparecer en la casa")
        for headers in (OWNER, SANDRA):
            for query in ("chat_id=22", "actor=owner", "recipient=33"):
                state = await (await self.get("state?" + query, headers)).json()
                self.assertEqual(state["wishes"][0]["id"], "sandra-wish")
                response = await self.get("events?animal=vaca&" + query, headers)
                # Rejecting extra parameters is also safe; accepting them must never rebind.
                if response.status == 200:
                    self.assertEqual([event["text"] for event in (await response.json())["events"]], ["Deseo de Sandra"])
                else:
                    self.assertEqual(response.status, 400)
                self.assertEqual((await self.get("history?animal=vaca&" + query, headers)).status, 400)
                self.assertEqual((await self.get("stories?" + query, headers)).status, 400)
                self.assertEqual((await self.get("story?id=7&" + query, headers)).status, 400)
        for invalid_actor in ("admin", "33", ""):
            self.assertEqual((await self.get("state", {**OWNER, "X-Castori-Actor": invalid_actor})).status, 403)

    async def test_receipts_keep_authenticated_actor_scope_despite_shared_reads(self):
        self.data["web_bridge"] = {"sequence": 0, "inboxes": {}, "requests": {
            "11:sharedreceipt": {"status": "processed"},
            "22:sharedreceipt": {"status": "uncertain"},
            "22:adminreceipt": {"status": "processed", "admin": True}}}
        owner = await (await self.get("request?request_id=sharedreceipt")).json()
        sandra = await (await self.get("request?request_id=sharedreceipt", SANDRA)).json()
        self.assertEqual(owner["status"], "uncertain")
        self.assertEqual(sandra["status"], "processed")
        response = await self.get("request?request_id=sharedreceipt&chat_id=11&actor=sandra")
        if response.status == 200:
            self.assertEqual((await response.json())["status"], "uncertain")
        else:
            self.assertEqual(response.status, 400)
        self.assertEqual((await self.get("request?request_id=adminreceipt", SANDRA)).status, 404)
        self.assertEqual((await self.get("request?request_id=adminreceipt")).status, 423)
        self.access.status.return_value["unlocked"] = True
        self.assertEqual((await self.get("request?request_id=adminreceipt")).status, 200)

    async def test_portal_owner_admin_guard_only_uses_validated_database_session(self):
        self.bridge.record_admin(22, "Sorpresa reservada al propietario")
        valid = {"Cookie": COOKIE + "=owner", "X-Castori-Actor": "sandra"}
        response = await self.get("admin-state", valid, "/api/bridge/")
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["actor"], "owner")
        auth = await (await self.get("admin-auth", valid, "/api/bridge/")).json()
        self.assertTrue(auth["permission_based"])
        self.assertTrue(auth["unlocked"])
        self.access.status.assert_not_awaited()
        for cookie, expected in (("sandra", 403), ("missing", 401)):
            forged = {**OWNER, "Cookie": COOKIE + "=" + cookie,
                      "X-Castori-Portal-Owner": "true", "X-Castori-Admin-Session": "forged"}
            for route in ("admin-state", "admin-events", "admin-auth", "admin-invitation", "admin-owner-invitation"):
                self.assertEqual((await self.get(route, forged, "/api/bridge/")).status, expected)
        self.sessions["mismatch"] = {**self.sessions["owner"], "chat_id": 11}
        self.assertEqual((await self.get("admin-state", {"Cookie": COOKIE + "=mismatch"}, "/api/bridge/")).status, 401)
        # The header name cannot activate the portal-only password bypass on the server bridge.
        self.assertEqual((await self.get("admin-state", {**OWNER, "X-Castori-Portal-Owner": "true"})).status, 423)

    async def test_missing_sandra_mapping_cannot_fall_back_to_owner_house(self):
        for identity in (None, 0, True, 22):
            self.identities["sandra"] = identity
            for route in ("state", "events?animal=vaca", "history?animal=vaca", "stories", "story?id=7"):
                with self.subTest(identity=identity, route=route):
                    self.assertEqual((await self.get(route)).status, 503)
        self.provider.page.assert_not_awaited()
        self.provider.stories.assert_not_awaited()
        self.provider.story.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
