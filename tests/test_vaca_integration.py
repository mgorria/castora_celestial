"""Offline checks of identity binding, private admin routing and durable storage."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import main


def update(text="/start", user_id=2, chat_id=None, chat_type="private"):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_chat=SimpleNamespace(id=chat_id if chat_id is not None else user_id,
                                       type=chat_type, send_message=AsyncMock()),
        message=SimpleNamespace(text=text),
    )


class IdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_uppercase_admin_error_never_logs_private_update(self):
        incoming = update("/VACA_VISITA 10/12/2026 09:00 | secreto", user_id=1)
        with patch.object(main, "vaca_error_handler", new_callable=AsyncMock) as private_error, \
             patch.object(main.logger, "exception") as log:
            await main.error_handler(incoming, SimpleNamespace(error=OSError("failed")))
        private_error.assert_awaited_once()
        log.assert_not_called()

    async def test_owner_test_does_not_bind_sandra(self):
        bot = MagicMock(allowed=lambda value: True, welcome=AsyncMock())
        with patch.object(main, "vaca", bot), patch.object(main, "owner_chat_id", return_value=1), \
             patch.object(main, "set_partner_chat_id") as bind, patch.object(main, "mark_seen_start") as mark:
            await main.animal_start("vaca", update(user_id=1), None)
        bind.assert_not_called()
        mark.assert_not_called()
        bot.welcome.assert_awaited_once()

    async def test_unknown_start_cannot_overwrite_binding(self):
        bot = MagicMock(allowed=lambda value: False)
        with patch.object(main, "vaca", bot), patch.object(main, "set_partner_chat_id") as bind:
            await main.animal_start("vaca", update(user_id=99), None)
        bind.assert_not_called()

    async def test_known_sandra_start_binds_and_welcomes(self):
        bot = MagicMock(allowed=lambda value: True, welcome=AsyncMock())
        with patch.object(main, "vaca", bot), patch.object(main, "owner_chat_id", return_value=1), \
             patch.object(main, "set_partner_chat_id") as bind, patch.object(main, "mark_seen_start"), \
             patch.object(main, "has_seen_start", return_value=False), \
             patch.object(main, "notify_animal_ready", new_callable=AsyncMock):
            await main.animal_start("vaca", update(), None)
        bind.assert_called_once_with("vaca", 2)
        bot.welcome.assert_awaited_once()

    async def test_private_plan_never_runs_from_group_or_partner(self):
        campaigns = SimpleNamespace(handle_admin=AsyncMock())
        with patch.object(main, "vaca_campaigns", campaigns), patch.object(main, "vaca", object()), \
             patch.object(main, "owner_chat_id", return_value=1):
            group = update("/vaca_visitas", user_id=1, chat_id=-100, chat_type="group")
            partner = update("/vaca_visitas", user_id=2)
            await main.central_vaca(group, SimpleNamespace(args=[]))
            await main.central_vaca(partner, SimpleNamespace(args=[]))
        campaigns.handle_admin.assert_not_awaited()
        group.effective_chat.send_message.assert_not_awaited()
        partner.effective_chat.send_message.assert_not_awaited()

    async def test_private_owner_can_manage_plan(self):
        campaigns = SimpleNamespace(handle_admin=AsyncMock())
        incoming = update("/vaca_visitas", user_id=1)
        with patch.object(main, "vaca_campaigns", campaigns), patch.object(main, "vaca", object()), \
             patch.object(main, "owner_chat_id", return_value=1):
            await main.central_vaca(incoming, SimpleNamespace(args=[]))
        campaigns.handle_admin.assert_awaited_once()

    async def test_send_requires_authorized_identity(self):
        with patch.object(main, "vaca_authorized_users", return_value={1, 2}):
            with self.assertRaises(ValueError):
                await main.vaca_send(99, "secreto")

    async def test_failed_public_send_never_enters_memory(self):
        bot = MagicMock()
        with patch.object(main, "vaca", bot), \
             patch.object(main, "vaca_send", new=AsyncMock(side_effect=TimeoutError)), \
             patch.object(main, "append_history") as append:
            with self.assertRaises(TimeoutError):
                await main.vaca_send_public(2, "pista")
        bot.remember_outgoing.assert_not_called()
        append.assert_not_called()

    def test_recipient_requires_this_bot_start(self):
        with patch.object(main, "vaca_partner_id", return_value=2), \
             patch.object(main, "get_partner_chat_id", return_value=2), \
             patch.object(main, "has_seen_start", return_value=False):
            self.assertIsNone(main.vaca_recipient())
        with patch.object(main, "vaca_partner_id", return_value=2), \
             patch.object(main, "get_partner_chat_id", return_value=2), \
             patch.object(main, "has_seen_start", return_value=True):
            self.assertEqual(main.vaca_recipient(), 2)


class StorageTests(unittest.TestCase):
    def test_atomic_save_preserves_other_animals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.json"
            with patch.object(main, "DATA_FILE", path):
                main.save_data({"mimosuga": {"keep": True}, "vaca": {"sessions": {}}})
                data = main.load_data()
                data["vaca"]["sessions"]["2"] = {"wishes": [{"name": "Libro"}]}
                main.save_data(data)
            self.assertTrue(json.loads(path.read_text())["mimosuga"]["keep"])
            self.assertFalse(path.with_name("data.json.tmp").exists())


if __name__ == "__main__":
    unittest.main()
