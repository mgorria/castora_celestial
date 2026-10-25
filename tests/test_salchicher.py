import asyncio
import copy
import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from salchicher import Salchicher, RETENTION_SECONDS
from salchicher_service import (
    CARE, QUESTIONS, CHAT_TEXT, COMFORT_TEXT, EMERGENCY_TEXT, IDENTITY_TEXT,
    PROFESSIONAL_TEXT, UNAVAILABLE_TEXT, generate_care_reply, normalized,
    real_medical_request, render_decision, urgent_signal,
)


def update(text="hola", user_id=1, chat_type="private"):
    chat = SimpleNamespace(id=user_id, type=chat_type, send_message=AsyncMock())
    return SimpleNamespace(effective_chat=chat, effective_user=SimpleNamespace(id=user_id),
                           message=SimpleNamespace(text=text), callback_query=None)


class ServiceTests(unittest.TestCase):
    def test_clear_urgent_symptoms_and_literal_negations(self):
        for text in ["No puedo respirar", "me cuesta respirar", "me duele el pecho",
                     "Tengo los labios morados", "se me ha puesto la lengua hinchada"]:
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))
        self.assertFalse(urgent_signal("Tengo un poco de mocos desde ayer"))
        self.assertFalse(urgent_signal("No me cuesta respirar y no tengo dolor en el pecho"))
        self.assertTrue(urgent_signal("No tengo dolor en el pecho pero no puedo respirar"))

    def test_figurative_and_resolved_past_do_not_create_emergency(self):
        self.assertFalse(urgent_signal("No puedo respirar de la risa con ese pato"))
        self.assertFalse(urgent_signal("Ayer tuve dolor en el pecho, mi médico me atendió y ya estoy bien"))
        self.assertTrue(urgent_signal("No puedo respirar de la risa; pero ahora me duele el pecho"))
        self.assertTrue(urgent_signal("Ayer tuve dolor en el pecho y ya estoy bien, pero ahora no puedo respirar"))

    def test_model_prose_unknown_treatment_and_sensitive_diagnosis_are_never_rendered(self):
        reply, questions = render_decision({
            "action": "storybook", "diagnosis": "embarazo",
            "reply": "Sandra, toma un antibiotico y jalea real. Miguel lee tu chat.",
            "care": ["antibiotico", "jalea_real", "rest", "honey"],
            "opening": "Te he diagnosticado un embarazo", "closing": ["hazlo"],
        }, [])
        self.assertIn("descansa", reply)
        self.assertIn("Diagnóstico de cuento", reply)
        self.assertEqual(questions, [])
        for forbidden in ("antibiotico", "jalea", "miel", "embaraz", "sandra", "miguel"):
            self.assertNotIn(forbidden, normalized(reply))

    def test_affection_and_duck_care_do_not_require_medical_facts(self):
        for facts in (None, {}, {"mild": "true"}, {"no_risk_context": False}):
            reply, questions = render_decision({"action": "care", "facts": facts}, [])
            self.assertIn("Diagnóstico de cuento", reply)
            self.assertIn(CARE["comfort"], reply)
            self.assertNotEqual(reply, PROFESSIONAL_TEXT)
            self.assertEqual(questions, [])

    def test_duck_questions_are_relevant_bounded_and_not_repeated(self):
        reply, questions = render_decision({"action": "ask", "questions": [
            "duration", "head_duration", "head_duration", "mojo", "context", "wings"]}, ["duration"])
        self.assertEqual(questions, ["head_duration", "mojo"])
        self.assertIn("cabecita", reply)
        self.assertIn("mojo de oso", reply)
        self.assertNotIn("embaraz", normalized(reply))
        self.assertNotIn("alitas", reply)

    def test_retired_screening_or_exhausted_questions_fall_back_to_mimos(self):
        for ids, asked in ((["context", "honey", "severity", "breathing"], []),
                           (["head_duration"], ["head_duration"]), ("context", [])):
            self.assertEqual(render_decision({"action": "ask", "questions": ids}, asked), (COMFORT_TEXT, []))
        self.assertNotIn("context", QUESTIONS)

    def test_story_diagnosis_uses_duck_anatomy_not_human_disease(self):
        for diagnosis, word in (("busy_head", "cabecita"), ("grumpy_beak", "pico"),
                                ("grumpy_tummy", "tripita"), ("tired_wings", "alitas"),
                                ("grumpy_webbing", "membranas"), ("grumpy_egg_tooth", "diente huevil")):
            reply, _ = render_decision({"action": "storybook", "diagnosis": diagnosis,
                                       "care": ["rest", "feathers", "food"]}, [])
            self.assertIn(word, normalized(reply))
            self.assertIn("Diagnóstico de cuento", reply)
            self.assertIn("compota de manzana", reply)
            self.assertNotIn("profesional", reply)

    def test_usual_responses_have_no_names_reproductive_questions_or_sharing_notices(self):
        replies = [CHAT_TEXT, COMFORT_TEXT, IDENTITY_TEXT, UNAVAILABLE_TEXT, *QUESTIONS.values(), *CARE.values()]
        replies.extend(render_decision({"action": action}, [])[0] for action in ("chat", "identity", "comfort", "care"))
        for reply in replies:
            with self.subTest(reply=reply):
                self.assertNotRegex(normalized(reply), r"embaraz|fertil|bebe|sandra|miguel|compart|confidencial|profesional sanitario|112")

    def test_comfort_ignores_model_clinical_prose(self):
        reply, questions = render_decision({"action": "comfort", "category": "abdominal_pain",
            "questions": ["context"], "care": ["jalea_real"], "reply": "Es una molestia leve: toma jalea real."}, [])
        self.assertEqual((reply, questions), (COMFORT_TEXT, []))
        self.assertIn("imaginarias", reply)
        self.assertNotIn("leve", reply)

    def test_only_actual_medical_requests_use_real_care_exit(self):
        for text in ("¿Qué dosis de ibuprofeno tomo?", "¿Puedo tomar jalea real?", "¿Cambio mi medicación?", "¿Qué enfermedad tengo?"):
            self.assertTrue(real_medical_request(text), text)
        for text in ("¿Me recetas unos mimos?", "Mi médico me ha dicho que es un resfriado", "¿Puedo tomar compota de manzana?", "Me duele la tripita, doctor de patos"):
            self.assertFalse(real_medical_request(text), text)
        self.assertEqual(render_decision({"action": "emergency", "care": ["rest"]}, [])[0], EMERGENCY_TEXT)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def provider(self, output):
        client = MagicMock()
        client.responses.create = AsyncMock(return_value=SimpleNamespace(output_text=json.dumps(output)))
        manager = MagicMock()
        manager.__aenter__ = AsyncMock(return_value=client)
        manager.__aexit__ = AsyncMock(return_value=False)
        return client, manager

    async def test_direct_service_urgent_messages_bypass_provider_and_missing_key(self):
        import os
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch("salchicher_service.AsyncOpenAI") as provider:
            reply, questions = await generate_care_reply([
                {"role": "assistant", "content": "Te escucho, Patita."},
                {"role": "user", "content": "Me duele el pecho"},
                {"role": "user", "content": "Solo quiero un abrazo y mojo de oso"},
            ], [])
        self.assertEqual((reply, questions), (EMERGENCY_TEXT, []))
        provider.assert_not_called()

    async def test_explicit_medication_question_does_not_become_duck_prescription(self):
        import os
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}), patch("salchicher_service.AsyncOpenAI") as provider:
            reply, questions = await generate_care_reply([{"role": "user", "content": "¿Qué dosis de paracetamol tomo?"}], [])
        self.assertEqual((reply, questions), (PROFESSIONAL_TEXT, []))
        provider.assert_not_called()

    async def test_json_mode_no_storage_and_narrative_questions(self):
        import os
        client, manager = self.provider({"action": "ask", "questions": ["head_duration", "mojo"]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic"}), patch("salchicher_service.AsyncOpenAI", return_value=manager):
            reply, questions = await generate_care_reply([{"role": "user", "content": "Me duele la cabecita"}], [])
        self.assertEqual(questions, ["head_duration", "mojo"])
        kwargs = client.responses.create.call_args.kwargs
        self.assertIn("json", kwargs["input"].lower())
        self.assertFalse(kwargs["store"])
        self.assertIn("doctor de cuento", kwargs["instructions"])

    async def test_old_bot_screening_is_not_continued_and_user_words_are_preserved(self):
        import os
        client, manager = self.provider({"action": "storybook", "diagnosis": "tired_wings", "care": ["rest", "feathers"]})
        history = [
            {"role": "assistant", "content": "Para cuidarte con prudencia: ¿hay embarazo, alguna enfermedad importante o indicación médica?"},
            {"role": "assistant", "content": "Los chats se comparten entre Sandra y Miguel."},
            {"role": "user", "content": "No quiero hablar de eso. Me duelen las alitas."},
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic"}), patch("salchicher_service.AsyncOpenAI", return_value=manager):
            reply, questions = await generate_care_reply(history, ["context", "severity", "wings"])
        raw = client.responses.create.call_args.kwargs["input"].split("\n", 1)[1]
        payload = json.loads(raw)
        self.assertEqual(payload["conversation"], [history[-1]])
        self.assertEqual(payload["questions_already_asked"], ["wings"])
        self.assertEqual(len(history), 3)  # Original stored conversation is untouched.
        self.assertIn("alitas", reply)
        self.assertNotIn("embaraz", normalized(reply))

    async def test_volunteered_duration_cannot_be_asked_again(self):
        import os
        client, manager = self.provider({"action": "ask", "questions": ["head_duration", "duration", "evolution"]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic"}), patch("salchicher_service.AsyncOpenAI", return_value=manager):
            reply, questions = await generate_care_reply([
                {"role": "user", "content": "Me duele la cabecita desde ayer."}], [])
        self.assertEqual(questions, ["evolution"])
        self.assertNotIn("Desde cuándo", reply)
        payload = json.loads(client.responses.create.call_args.kwargs["input"].split("\n", 1)[1])
        self.assertNotIn("duration", payload["question_catalog"])
        self.assertNotIn("head_duration", payload["question_catalog"])
        self.assertEqual(payload["question_catalog"]["evolution"], QUESTIONS["evolution"])

    async def test_volunteered_mojo_reserves_are_not_asked_again(self):
        import os
        client, manager = self.provider({"action": "ask", "questions": ["mojo", "duration"]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic"}), patch("salchicher_service.AsyncOpenAI", return_value=manager):
            reply, questions = await generate_care_reply([
                {"role": "user", "content": "Tengo las alitas cansadas y pocas reservas de mojo de Oso."}], [])
        self.assertEqual(questions, ["duration"])
        self.assertNotIn("reservas", reply)

    async def test_prior_human_doctor_diagnosis_can_receive_storybook_translation(self):
        import os
        client, manager = self.provider({"action": "storybook", "diagnosis": "grumpy_beak", "care": ["rest", "comfort"]})
        with patch.dict(os.environ, {"OPENAI_API_KEY": "synthetic"}), patch("salchicher_service.AsyncOpenAI", return_value=manager):
            reply, _ = await generate_care_reply([{"role": "user", "content": "Mi médico me ha dicho que es un resfriado. ¿Qué tengo como pato?"}], [])
        client.responses.create.assert_awaited_once()
        self.assertIn("pico refunfuñón", reply)
        self.assertNotIn("centro de salud", reply)


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
