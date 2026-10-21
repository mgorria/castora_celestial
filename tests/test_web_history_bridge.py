"""Authenticated history HTTP and durable outbox tests; all providers are offline."""

import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import ClientTimeout
from aiohttp.test_utils import TestClient, TestServer

from web_bridge import MAX_EVENTS, WebBridge


TOKEN = "test-history-bridge-secret-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Castori-Actor": "sandra"}


class HistoryBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"salchicher": {"sessions": {"11": {"updated_at": time.time(), "shared": False}}}}
        self.provider = SimpleNamespace(
            initialize=AsyncMock(), record_event=AsyncMock(return_value=True), forget=AsyncMock(return_value=True),
            page=AsyncMock(return_value={"messages": [], "has_more": False, "next_cursor": None, "archive_available": True}),
            stories=AsyncMock(return_value={"stories": [], "has_more": False, "next_cursor": None, "archive_available": True}),
            story=AsyncMock(return_value=None),
        )
        self.bridge = self.new_bridge()
        self.client = TestClient(TestServer(self.bridge.create_app()), timeout=ClientTimeout(total=5))
        await self.client.start_server()

    def new_bridge(self):
        def save(data):
            self.data = copy.deepcopy(data)
        return WebBridge(lambda: copy.deepcopy(self.data), save, lambda: {},
                         lambda actor: {"sandra": 11, "owner": 22}.get(actor), token=TOKEN,
                         history_provider=self.provider)

    async def asyncTearDown(self):
        await self.bridge.close()
        await self.client.close()

    async def get(self, suffix, actor="sandra", authenticated=True):
        headers = {**HEADERS, "X-Castori-Actor": actor} if authenticated else {}
        return await self.client.get("/castori-web/" + suffix, headers=headers)

    async def test_history_routes_require_authentication_and_take_identity_from_server(self):
        for route in ("history?animal=mimosuga", "stories", "story?id=7"):
            self.assertEqual((await self.get(route, authenticated=False)).status, 401)
        response = await self.get("history?animal=mimosuga&limit=20&before=YWJj", actor="owner")
        self.assertEqual(response.status, 200)
        self.provider.page.assert_awaited_once_with("owner", 22, "mimosuga", before="YWJj", limit=20)
        response = await self.get("stories?limit=5")
        self.assertEqual(response.status, 200)
        self.provider.stories.assert_awaited_once_with("sandra", 11, before=None, limit=5)
        self.provider.story.return_value = {"story": {"id": 7, "full_text": "Cuento entregado"}}
        response = await self.get("story?id=7")
        self.assertEqual((await response.json())["story"]["full_text"], "Cuento entregado")
        self.provider.story.assert_awaited_once_with("sandra", 11, 7)

    async def test_strict_queries_cannot_select_a_different_identity_or_unbounded_page(self):
        invalid = ("history?animal=mimosuga&chat_id=22", "history?animal=mimosuga&limit=0",
                   "history?animal=mimosuga&limit=101", "history?animal=mimosuga&limit=2&limit=3",
                   "history?animal=mimosuga&before=with.dot", "history?animal=mimosuga&before=" + "a" * 513,
                   "history?animal=unknown", "history", "stories?limit=51", "stories?actor=owner",
                   "story?id=-1", "story?id=0", "story?id=01", "story?id=9223372036854775808",
                   "story?id=7&id=8", "story?id=7&chat_id=22")
        for route in invalid:
            with self.subTest(route=route[:100]):
                self.assertEqual((await self.get(route)).status, 400)
        self.provider.page.assert_not_awaited()
        self.provider.stories.assert_not_awaited()
        self.provider.story.assert_not_awaited()

    async def test_private_doctor_never_reaches_archive_provider(self):
        self.assertEqual((await self.get("history?animal=salchicher")).status, 403)
        self.bridge.record("salchicher", 11, "PRIVADO", role="user")
        self.bridge.record("salchicher", 11, "RESPUESTA PRIVADA")
        await self.bridge.flush_history()
        self.assertEqual(self.data.get("history_outbox", []), [])
        self.provider.record_event.assert_not_awaited()
        self.provider.page.assert_not_awaited()

    async def test_unavailable_is_not_reported_as_an_empty_archive(self):
        self.provider.page.return_value["archive_available"] = False
        self.assertEqual((await self.get("history?animal=mimosuga")).status, 503)
        self.provider.page.return_value["messages"] = [{"id": "legacy:1", "text": "Fragmento local"}]
        response = await self.get("history?animal=mimosuga")
        self.assertEqual(response.status, 200)
        self.assertFalse((await response.json())["archive_available"])
        self.provider.page.side_effect = ValueError("different actor cursor")
        self.assertEqual((await self.get("history?animal=mimosuga&before=YWJj")).status, 400)
        self.provider.page.side_effect = RuntimeError("database down")
        self.assertEqual((await self.get("history?animal=mimosuga")).status, 503)
        self.provider.stories.side_effect = RuntimeError("database down")
        self.assertEqual((await self.get("stories")).status, 503)
        self.assertEqual((await self.get("story?id=7")).status, 404)
        self.provider.story.side_effect = RuntimeError("database down")
        self.assertEqual((await self.get("story?id=7")).status, 503)

    async def test_provider_is_optional_and_missing_provider_returns_unavailable(self):
        self.bridge.history_provider = None
        for route in ("history?animal=mimosuga", "stories", "story?id=7"):
            self.assertEqual((await self.get(route)).status, 503)

    async def test_outbox_is_durable_before_ring_truncation_and_retries_without_relaying(self):
        self.provider.record_event.return_value = False
        for number in range(MAX_EVENTS + 5):
            self.bridge.record("mimosuga", 11, f"Mensaje {number}", message_id=number)
        self.assertEqual(len(self.data["web_bridge"]["inboxes"]["11:mimosuga"]), MAX_EVENTS)
        self.assertEqual(len(self.data["history_outbox"]), MAX_EVENTS + 5)
        self.bridge.record("mimosuga", 11, "Repetido", message_id=MAX_EVENTS + 4)
        self.assertEqual(len(self.data["history_outbox"]), MAX_EVENTS + 5)
        await self.bridge.flush_history()
        self.assertEqual(len(self.data["history_outbox"]), MAX_EVENTS + 5)
        self.provider.record_event.return_value = True
        restarted = self.new_bridge()
        await restarted.start(port=0)
        self.assertEqual(self.data["history_outbox"], [])
        self.assertTrue(all(call.args[0] == "mimosuga" and call.args[1] == 11
                            for call in self.provider.record_event.await_args_list))
        await restarted.close()

    async def test_start_initializes_before_importing_existing_inboxes_and_close_flushes(self):
        self.bridge.history_provider = None
        event = self.bridge.record("castori", 11, "Anterior al archivo", message_id=9)
        self.bridge.history_provider = self.provider
        order = []
        async def initialize():
            order.append("initialize")
        async def record(animal, chat_id, incoming, *, epoch):
            order.append("record")
            self.assertEqual(incoming["id"], event["id"])
            return True
        self.provider.initialize.side_effect = initialize
        self.provider.record_event.side_effect = record
        await self.bridge.start(port=0)
        self.assertEqual(order, ["initialize", "record"])
        self.provider.record_event.side_effect = None
        self.bridge.record("castori", 11, "Al cerrar", message_id=10)
        self.assertEqual(len(self.data["history_outbox"]), 1)
        await self.bridge.close()
        self.assertEqual(self.data["history_outbox"], [])

    async def test_forget_purges_only_vaca_scope_and_retries_before_archiving_new_epoch(self):
        self.data["history_baseline"] = {"version": 1, "scopes": {"11:vaca": {"epoch": 0, "messages": ["Antiguo"]},
                                                                      "22:vaca": {"epoch": 0, "messages": ["Del dueño"]}}}
        self.data["vaca"] = {"sessions": {"11": {"wishes": [{"name": "Libro"}]}}}
        self.bridge.record("vaca", 11, "A borrar", message_id=1)
        self.bridge.record("vaca", 22, "Del dueño", message_id=2)
        self.bridge.forget("vaca", 11)
        self.assertNotIn("11:vaca", self.data["history_baseline"]["scopes"])
        self.assertIn("22:vaca", self.data["history_baseline"]["scopes"])
        self.assertEqual([item["chat_id"] for item in self.data["history_outbox"]], [22])
        self.assertEqual(self.data["vaca"]["sessions"]["11"]["wishes"], [{"name": "Libro"}])
        fresh = self.bridge.record("vaca", 11, "Después de olvidar", message_id=3)
        self.provider.forget.return_value = False
        await self.bridge.flush_history()
        self.assertTrue(self.data["history_forgets"]["11:vaca"]["pending"])
        self.assertEqual(len(self.data["history_outbox"]), 1)
        self.assertEqual(self.data["history_outbox"][0]["epoch"], 1)
        self.provider.forget.return_value = True
        order = []
        async def forget(*args, **kwargs):
            order.append("forget")
            return True
        async def record(*args, **kwargs):
            order.append("record")
            self.assertEqual(args[2]["id"], fresh["id"])
            self.assertEqual(kwargs["epoch"], 1)
            return True
        self.provider.forget.side_effect, self.provider.record_event.side_effect = forget, record
        await self.bridge.flush_history()
        self.assertEqual(order, ["forget", "record"])
        self.assertEqual(self.data["history_outbox"], [])
        self.assertEqual(self.data["history_forgets"]["11:vaca"]["epoch"], 1)
        self.assertFalse(self.data["history_forgets"]["11:vaca"]["pending"])

    async def test_forget_during_an_await_cannot_acknowledge_or_erase_new_outbox_records(self):
        started, release = asyncio.Event(), asyncio.Event()
        async def delayed(*args, **kwargs):
            started.set()
            await release.wait()
            return True
        self.provider.record_event.side_effect = delayed
        self.bridge.record("vaca", 11, "Antiguo", message_id=1)
        flushing = asyncio.create_task(self.bridge.flush_history())
        await asyncio.wait_for(started.wait(), 2)
        self.bridge.forget("vaca", 11)
        fresh = self.bridge.record("vaca", 11, "Nuevo", message_id=2)
        release.set()
        await asyncio.wait_for(flushing, 2)
        self.assertEqual([item["event"]["id"] for item in self.data["history_outbox"]], [fresh["id"]])
        self.assertTrue(self.data["history_forgets"]["11:vaca"]["pending"])
        self.provider.record_event.side_effect = None


if __name__ == "__main__":
    unittest.main()
