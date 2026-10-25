"""Read receipts and portal delivery use local HTTP and mocked Telegram only."""

import copy
import os
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from aiohttp.test_utils import TestClient, TestServer
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, User
from telegram.ext import ExtBot

import unread_notifications as unread
from web_bridge import RecordingExtBot, WebBridge


TOKEN = "offline-bridge-secret-at-least-32-characters"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "X-Castori-Actor": "sandra"}


class UnreadBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {}
        unread.initialize(self.data)

        def save(data):
            self.data = copy.deepcopy(data)

        self.doctor = SimpleNamespace(maintenance=Mock(), get_consultation=Mock())
        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), save, lambda: {},
            lambda actor: {"sandra": 11, "owner": 22}.get(actor), token=TOKEN,
            portal_origin="https://portal.example", get_consultorio=lambda: self.doctor)
        self.client = TestClient(TestServer(self.bridge.create_app()))
        await self.client.start_server()
        self.setting = patch.dict(os.environ, {"CASTORI_WEB_ONLY_DELIVERY": "true"})
        self.setting.start()

    async def asyncTearDown(self):
        self.setting.stop()
        await self.client.close()

    def bot(self, animal="mimosuga"):
        bot = RecordingExtBot(token="123:offline", bridge=self.bridge, animal_key=animal)
        bot._bot_user = User(123, "Animal", is_bot=True, username="OfflineAnimal_bot")
        return bot

    async def read(self, event, *, animal=None, headers=None, consultation_id=None):
        return await self.client.post("/castori-web/read", json={
            "animal": animal or event["animal"], "event_id": event["id"],
            "consultation_id": consultation_id}, headers=HEADERS if headers is None else headers)

    async def test_only_sandra_acknowledges_and_get_does_not_mark_read(self):
        event = self.bridge.record("mimosuga", 11, "Carta nueva", source="web")
        for headers in (HEADERS, {**HEADERS, "X-Castori-Actor": "owner"}):
            response = await self.client.get("/castori-web/events?animal=mimosuga", headers=headers)
            self.assertEqual(response.status, 200)
            self.assertEqual(len(unread.pending(self.data, 11)), 1)
        response = await self.read(event, headers={**HEADERS, "X-Castori-Actor": "owner"})
        self.assertEqual(response.status, 403)
        response = await self.read(event, headers={})
        self.assertEqual(response.status, 401)
        self.assertEqual(len(unread.pending(self.data, 11)), 1)
        response = await self.read(event)
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"ok": True})
        self.assertEqual(unread.pending(self.data, 11), [])

    async def test_cursor_cannot_ack_future_another_animal_or_another_person(self):
        event = self.bridge.record("mimosuga", 11, "Su carta", source="web")
        owner_event = self.bridge.record("mimosuga", 22, "Carta del propietario", source="web")
        other = self.bridge.record("vaca", 11, "Otra carta", source="web")
        for candidate, animal in (({**event, "id": 9999}, None), (event, "vaca"),
                                  (owner_event, None), ({**event, "id": True}, None)):
            response = await self.read(candidate, animal=animal)
            self.assertEqual(response.status, 400)
        self.assertEqual({item["event_id"] for item in unread.pending(self.data, 11)},
                         {event["id"], other["id"]})

    async def test_late_receipt_leaves_new_message_pending_and_never_rewinds(self):
        old = self.bridge.record("mimosuga", 11, "Primera", source="web")
        new = self.bridge.record("mimosuga", 11, "Segunda", source="web")
        self.assertEqual((await self.read(old)).status, 200)
        self.assertEqual(unread.pending(self.data, 11)[0]["event_id"], new["id"])
        self.assertEqual((await self.read(new)).status, 200)
        self.assertEqual((await self.read(old)).status, 200)
        self.assertEqual(unread.pending(self.data, 11), [])

    async def test_consultation_cursor_belongs_to_requested_episode(self):
        self.data["salchicher"] = {"sessions": {"11": {
            "consultation_id": "episode-old", "retained": True, "updated_at": time.time()}},
            "consultations": {"11": {"episode-old": {"retained": True}}}}
        first = self.bridge.record("salchicher", 11, "Primer episodio", source="web")
        self.data["salchicher"]["sessions"]["11"]["consultation_id"] = "episode-new"
        self.bridge.record("salchicher", 11, "Segundo episodio", source="web")
        item = {"id": "episode-old", "messages": [{"role": "assistant", "content": "Primer episodio"}]}
        self.doctor.get_consultation.return_value = item
        response = await self.client.get("/castori-web/consultation?id=episode-old", headers=HEADERS)
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"consultation": item, "read_cursor": first["id"]})
        self.assertEqual((await self.read(first, consultation_id="episode-new")).status, 400)
        self.assertEqual((await self.read(first, consultation_id="episode-old")).status, 200)
        self.assertEqual(unread.pending(self.data, 11)[0]["consultation_id"], "episode-new")

    async def test_sandra_messages_and_keyboard_edits_stay_in_portal(self):
        bot = self.bot()
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("Elegir", callback_data="cuento:one")]])
        with patch.object(ExtBot, "send_message", AsyncMock()) as send, \
             patch.object(ExtBot, "edit_message_reply_markup", AsyncMock()) as edit, \
             patch.object(ExtBot, "send_chat_action", AsyncMock()) as typing:
            message = await bot.send_message(11, "Elige tu cuento", reply_markup=buttons)
            self.assertLess(message.message_id, 0)
            self.assertEqual(message.text, "Elige tu cuento")
            self.assertEqual(message.reply_markup, buttons)
            result = await message.edit_reply_markup(reply_markup=None)
            self.assertIsNone(result.reply_markup)
            await bot.send_chat_action(11, "typing")
            send.assert_not_awaited()
            edit.assert_not_awaited()
            typing.assert_not_awaited()
        events = self.data["web_bridge"]["inboxes"]["11:mimosuga"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["buttons"], [])
        self.assertEqual(events[0]["source"], "web")
        self.assertEqual(len(unread.pending(self.data, 11)), 1)

    async def test_owner_and_centralita_keep_telegram_delivery(self):
        for animal, chat_id in (("mimosuga", 22), ("centralita", 22)):
            with self.subTest(animal=animal):
                bot = self.bot(animal)
                delivered = Message.de_json({"message_id": 88, "date": int(time.time()),
                    "chat": {"id": chat_id, "type": "private"}, "text": "Prueba"}, bot)
                with patch.object(ExtBot, "send_message", AsyncMock(return_value=delivered)) as send:
                    self.assertIs(await bot.send_message(chat_id, "Prueba"), delivered)
                    send.assert_awaited_once_with(chat_id, "Prueba")
        self.assertEqual(unread.pending(self.data, 11), [])

    async def test_notification_bypasses_history_and_is_castori_to_sandra_only(self):
        bot = self.bot("castori")
        before = copy.deepcopy(self.data)
        with patch.object(ExtBot, "send_message", AsyncMock()) as send:
            await bot.send_notification(11, "Hay cartas sin leer")
            send.assert_awaited_once_with(11, "Hay cartas sin leer")
            with self.assertRaises(ValueError):
                await bot.send_notification(22, "No enviar")
            with self.assertRaises(ValueError):
                await self.bot("mimosuga").send_notification(11, "No enviar")
            self.assertEqual(send.await_count, 1)
        self.assertEqual(self.data, before)

    async def test_failed_portal_save_never_falls_back_to_telegram(self):
        bot = self.bot()
        with patch.object(self.bridge, "save", side_effect=OSError("disk unavailable")), \
             patch.object(ExtBot, "send_message", AsyncMock()) as send:
            with self.assertRaises(OSError):
                await bot.send_message(11, "No duplicar")
            send.assert_not_awaited()
        self.assertEqual(unread.pending(self.data, 11), [])


if __name__ == "__main__":
    unittest.main()
