import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from salchicher import Salchicher, RETENTION_SECONDS
from salchicher_service import EMERGENCY_TEXT, PROFESSIONAL_TEXT, UNAVAILABLE_TEXT, render_decision, urgent_signal


def update(text="hola", user_id=1, chat_type="private"):
    chat = SimpleNamespace(id=user_id, type=chat_type, send_message=AsyncMock())
    return SimpleNamespace(effective_chat=chat, effective_user=SimpleNamespace(id=user_id),
                           message=SimpleNamespace(text=text), callback_query=None)


class ServiceTests(unittest.TestCase):
    def test_clear_urgent_symptoms(self):
        for text in ["No puedo respirar", "me cuesta respirar", "me duele el pecho",
                     "Tengo los labios morados", "se me ha puesto la lengua hinchada"]:
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))
        self.assertFalse(urgent_signal("Tengo un poco de mocos desde ayer"))
        self.assertFalse(urgent_signal("No me cuesta respirar y no tengo dolor en el pecho"))
        self.assertTrue(urgent_signal("No tengo dolor en el pecho pero no puedo respirar"))

    def test_model_text_and_unknown_care_never_reach_patient(self):
        reply, _ = render_decision({
            "action": "care", "category": "mild_respiratory",
            "reply": "Toma un antibiotico", "care": ["antibiotico", "jalea_real", "rest", "honey"],
            "facts": {key: True for key in ["mild", "recent", "stable_or_improving", "breathing_normal",
                                            "swallowing_normal", "no_risk_context", "no_persistent_or_high_fever"]},
        }, [])
        self.assertIn("descansa", reply)
        self.assertNotIn("antibiotico", reply)
        self.assertNotIn("jalea", reply)
        self.assertNotIn("miel", reply)

    def test_missing_or_string_facts_cannot_allow_care(self):
        for facts in [{}, {"mild": "true"}, {"mild": True, "recent": False}]:
            reply, _ = render_decision({"action": "care", "facts": facts}, [])
            self.assertEqual(reply, PROFESSIONAL_TEXT)

    def test_no_repeated_questions(self):
        reply, questions = render_decision({"action": "ask", "questions": ["duration", "duration", "severity"]}, ["duration"])
        self.assertEqual(questions, ["severity"])
        self.assertNotIn("Desde cuando", reply)

    def test_emergency_not_replaced_by_care(self):
        self.assertEqual(render_decision({"action": "emergency", "care": ["honey"]}, [])[0], EMERGENCY_TEXT)


class ConversationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {}
        self.send = AsyncMock()
        self.notify = AsyncMock()
        def save(data):
            self.data = copy.deepcopy(data)
        self.bot = Salchicher(lambda: copy.deepcopy(self.data), save, lambda: {1, 2},
                              self.send, self.notify, idle_seconds=1)
        self.bot.idle_seconds = 0.01

    async def asyncTearDown(self):
        await self.bot.close()

    def seed(self, shared=False):
        self.bot.set_session(1, {"shared": shared, "history": [], "asked": [],
                                "version": 1, "pending": False, "updated_at": time.time()})

    async def finish(self):
        await asyncio.wait_for(asyncio.gather(*list(self.bot.tasks.values())), timeout=2)

    async def test_consent_before_processing_or_storing_health_text(self):
        incoming = update("Me pica la garganta")
        await self.bot.receive(incoming, None)
        incoming.effective_chat.send_message.assert_awaited_once()
        self.assertIsNone(self.bot.session(1))
        self.send.assert_not_awaited()
        self.notify.assert_not_awaited()

    async def test_unknown_user_and_group_are_rejected(self):
        for incoming in [update(user_id=3), update(chat_type="group")]:
            await self.bot.receive(incoming, None)
            incoming.effective_chat.send_message.assert_not_awaited()
        self.assertFalse(self.data)

    async def test_four_messages_form_one_reply_and_private_stays_private(self):
        self.seed()
        generation = AsyncMock(return_value=("Una pregunta", ["duration"]))
        with patch("salchicher.generate_care_reply", generation):
            for text in ["hola", "me pica la garganta", "desde ayer", "un poquito"]:
                await self.bot.receive(update(text), None)
            await self.finish()
        generation.assert_awaited_once()
        self.assertEqual(len(generation.call_args.args[0]), 4)
        self.send.assert_awaited_once_with(1, "Una pregunta")
        self.notify.assert_not_awaited()
        self.assertEqual(self.bot.session(1)["asked"], ["duration"])

    async def test_shared_session_sends_one_summary(self):
        self.seed(shared=True)
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("Pregunta", []))):
            await self.bot.receive(update("mocos"), None)
            await self.bot.receive(update("desde ayer"), None)
            await self.finish()
        self.notify.assert_awaited_once()
        self.assertIn("mocos\ndesde ayer", self.notify.call_args.args[0])

    async def test_new_message_during_generation_discards_stale_answer(self):
        self.seed()
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []
        async def generate(history, asked):
            calls.append(history)
            if len(calls) == 1:
                started.set()
                await release.wait()
                return "respuesta obsoleta", []
            return "respuesta actual", []
        with patch("salchicher.generate_care_reply", generate):
            await self.bot.receive(update("mocos"), None)
            await asyncio.wait_for(started.wait(), 1)
            await self.bot.receive(update("tambien tos"), None)
            release.set()
            await self.finish()
        self.send.assert_awaited_once_with(1, "respuesta actual")
        self.assertEqual(len(calls), 2)

    async def test_off_cancels_inflight_reply_and_on_does_not_replay(self):
        self.seed()
        started = asyncio.Event()
        async def generate(*args):
            started.set()
            await asyncio.Event().wait()
        with patch("salchicher.generate_care_reply", generate):
            await self.bot.receive(update("mocos"), None)
            await asyncio.wait_for(started.wait(), 1)
            tasks = list(self.bot.tasks.values())
            self.bot.set_enabled(False)
            await asyncio.gather(*tasks, return_exceptions=True)
            self.bot.set_enabled(True)
            self.bot.maintenance()
        self.send.assert_not_awaited()
        self.assertFalse(self.bot.tasks)

    async def test_emergency_works_without_consent_model_or_enabled_switch(self):
        self.bot.set_enabled(False)
        with patch("salchicher.generate_care_reply", AsyncMock()) as generation:
            await self.bot.receive(update("No puedo respirar"), None)
        self.send.assert_awaited_once_with(1, EMERGENCY_TEXT)
        generation.assert_not_awaited()
        self.notify.assert_not_awaited()

    async def test_generation_error_keeps_service_responsive(self):
        self.seed()
        with patch("salchicher.generate_care_reply", AsyncMock(side_effect=ValueError("bad JSON"))):
            await self.bot.receive(update("tos"), None)
            await self.finish()
        self.send.assert_awaited_once_with(1, UNAVAILABLE_TEXT)
        self.assertFalse(self.bot.session(1)["pending"])

    async def test_delivery_timeout_is_not_automatically_retried(self):
        self.seed()
        self.send.side_effect = TimeoutError()
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("respuesta", []))):
            await self.bot.receive(update("tos"), None)
            await self.finish()
            self.bot.maintenance()
        self.send.assert_awaited_once()
        self.assertFalse(self.bot.session(1)["pending"])
        self.assertFalse(self.bot.tasks)

    async def test_retention_and_recovery(self):
        self.seed()
        session = self.bot.session(1)
        session.update(pending=True, due_at=time.time() - 1)
        self.bot.set_session(1, session)
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("retomado", []))):
            self.bot.maintenance()
            await self.finish()
        self.send.assert_awaited_once_with(1, "retomado")
        session = self.bot.session(1)
        session["updated_at"] = time.time() - RETENTION_SECONDS - 1
        self.bot.set_session(1, session)
        self.bot.maintenance()
        self.assertEqual(self.bot.state()["sessions"], {})

    async def test_forgetting_cancels_pending_messages(self):
        self.seed()
        await self.bot.receive(update("tos"), None)
        tasks = list(self.bot.tasks.values())
        await self.bot.reset(update(), None)
        await asyncio.gather(*tasks, return_exceptions=True)
        self.assertIsNone(self.bot.session(1))
        self.send.assert_not_awaited()


class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_registration_and_private_error_handler(self):
        import os
        import main
        bot = Salchicher(lambda: {}, lambda data: None, lambda: {1, 2}, AsyncMock(), AsyncMock())
        with patch.object(main, "salchicher", bot), patch.dict(os.environ, {
            "TOKEN_SALCHICHER": "123456:synthetic-test-token",
            "TOKEN_CENTRALITA": "234567:synthetic-test-token",
        }):
            animal_app = main.build_animal_app("salchicher")
            central_app = main.build_centralita_app()
        commands = {cmd for handler in animal_app.handlers[0] for cmd in getattr(handler, "commands", [])}
        self.assertTrue({"start", "consulta", "olvidar", "ayuda"}.issubset(commands))
        self.assertIn(main.salchicher_error_handler, animal_app.error_handlers)
        central_commands = {cmd for handler in central_app.handlers[0] for cmd in getattr(handler, "commands", [])}
        self.assertTrue({"salchicher", "salchicher_auto", "status"}.issubset(central_commands))

    async def test_owner_start_never_overwrites_partner(self):
        import main
        bot = Salchicher(lambda: {}, lambda data: None, lambda: {1, 2}, AsyncMock(), AsyncMock())
        with patch.object(main, "salchicher", bot), patch.object(main, "MI_CHAT_ID", "1"), \
             patch.object(main, "set_partner_chat_id") as bind:
            await main.animal_start("salchicher", update(user_id=1), None)
            await main.animal_start("salchicher", update(user_id=99), None)
        bind.assert_not_called()

    async def test_patient_cannot_turn_off_other_consultations(self):
        import main
        bot = SimpleNamespace(set_enabled=AsyncMock())
        with patch.object(main, "salchicher", bot), patch.object(main, "MI_CHAT_ID", "1"):
            await main.central_salchicher_auto(update(user_id=2), SimpleNamespace(args=["off"]))
        bot.set_enabled.assert_not_called()

    async def test_general_history_and_forwarding_are_not_used(self):
        import main
        bot = SimpleNamespace(receive=AsyncMock())
        with patch.object(main, "salchicher", bot), patch.object(main, "append_history") as append:
            await main.animal_message("salchicher", update("sintomas privados"), None)
        bot.receive.assert_awaited_once()
        append.assert_not_called()


if __name__ == "__main__":
    unittest.main()
