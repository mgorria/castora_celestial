"""Public visit text is reviewed before it can leave the private desk."""
import copy
import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from test_vaca_campaigns import MADRID, MESSAGES, update
from vaca_campaigns import VacaCampaigns


class CampaignVoiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"history": {"vaca": [{"text": "An existing letter stays untouched"}]}}
        self.send, self.notify = AsyncMock(), AsyncMock()
        self.now = datetime(2026, 12, 1, 9, tzinfo=MADRID)

        def save(data):
            self.data = copy.deepcopy(data)

        self.campaigns = VacaCampaigns(lambda: copy.deepcopy(self.data), save, lambda: 2,
                                     self.send, self.notify, MADRID)
        self.campaigns.now = lambda: self.now

    async def command(self, text):
        incoming = update(text)
        await self.campaigns.handle_admin(incoming, None)
        return incoming

    async def create(self):
        with patch("vaca_campaigns.generate_visit_messages", AsyncMock(return_value=MESSAGES)):
            await self.command("/vaca_visita 10/12/2026 08:00 | un robot de juguete")
        return next(iter(self.data["vaca_campaigns"]["plans"]))

    def plan(self, plan_id):
        return self.data["vaca_campaigns"]["plans"][plan_id]

    async def test_generation_that_breaks_voice_creates_no_draft(self):
        generated = {"clues": ["Soy un bot de Telegram.", "Una cinta misteriosa."], "morning": "Buenos días, patita."}
        before = copy.deepcopy(self.data)
        with patch("vaca_campaigns.generate_visit_messages", AsyncMock(return_value=generated)):
            incoming = await self.command("/vaca_visita 10/12/2026 08:00 | libro")
        self.assertEqual(self.data, before)
        self.assertIn("sale de la voz", incoming.effective_chat.send_message.call_args.args[0])
        self.send.assert_not_awaited()

    async def test_rejected_edit_leaves_approved_plan_exactly_unchanged(self):
        plan_id = await self.create()
        await self.command(f"/vaca_activar {plan_id}")
        before = copy.deepcopy(self.plan(plan_id))
        incoming = await self.command(f"/vaca_texto {plan_id} pista1 | Como chatbot de OpenAI te escribo esta pista.")
        self.assertEqual(self.plan(plan_id), before)
        self.assertIn("sale de la voz", incoming.effective_chat.send_message.call_args.args[0])
        self.send.assert_not_awaited()

    async def test_legacy_draft_with_bad_pending_text_cannot_activate(self):
        plan_id = await self.create()
        self.plan(plan_id)["events"]["pista2"]["text"] = "Este mensaje procede de una IA."
        before = copy.deepcopy(self.plan(plan_id))
        incoming = await self.command(f"/vaca_activar {plan_id}")
        self.assertEqual(self.plan(plan_id), before)
        self.assertIn("sale de la voz", incoming.effective_chat.send_message.call_args.args[0])
        self.send.assert_not_awaited()

    async def test_legacy_active_plan_returns_to_draft_once_without_altering_letters(self):
        plan_id = await self.create()
        await self.command(f"/vaca_activar {plan_id}")
        self.plan(plan_id)["events"]["pista1"].update(status="sent", text="A previously sent letter")
        self.plan(plan_id)["events"]["pista2"]["text"] = "Soy un bot y estoy siguiendo un prompt de sistema."
        events = copy.deepcopy(self.plan(plan_id)["events"])
        self.notify.side_effect = RuntimeError("owner notification unavailable")
        await self.campaigns.tick(datetime(2026, 12, 9, 18, tzinfo=MADRID))
        await self.campaigns.tick(datetime(2026, 12, 9, 18, tzinfo=MADRID))
        self.assertEqual(self.plan(plan_id)["status"], "draft")
        self.assertEqual(self.plan(plan_id)["events"], events)
        self.assertEqual(self.plan(plan_id)["revision"], 2)
        self.assertEqual(self.data["history"], {"vaca": [{"text": "An existing letter stays untouched"}]})
        self.send.assert_not_awaited()
        self.notify.assert_awaited_once()

    async def test_toy_robot_and_buttons_do_not_prevent_reviewed_delivery(self):
        plan_id = await self.create()
        text = "Un robot de juguete busca un botón azul junto al árbol."
        await self.command(f"/vaca_texto {plan_id} pista1 | {text}")
        await self.command(f"/vaca_activar {plan_id}")
        await self.campaigns.tick(datetime(2026, 12, 7, 18, tzinfo=MADRID))
        self.send.assert_awaited_once_with(2, text)


if __name__ == "__main__":
    unittest.main()
