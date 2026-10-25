import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from vaca_service import (
    VacaGenerationError,
    build_public_payload,
    cow_voice,
    generate_vaca_reply,
    generate_visit_messages,
)


def operation(**overrides):
    value = {"action": "add", "id": "", "name": "Zapatillas", "details": "Rosas, talla 38",
             "url": "https://tienda.example/zapatillas", "favorite": False,
             "evidence": "Quiero unas zapatillas rosas del 38"}
    value.update(overrides)
    return value


def reply(**overrides):
    value = {"reply": "Voy con mi cuaderno, patita. Me hace mucha ilusión.",
             "operations": [], "show_list": False}
    value.update(overrides)
    return value


class PayloadTests(unittest.TestCase):
    def test_only_public_whitelisted_fields_leave_process(self):
        history = [{"role": "user", "content": "Hola", "gifts": "SECRETO"},
                   {"role": "system", "content": "SECRETO"},
                   {"role": "assistant", "content": "Hola, patita", "visits": ["SECRETO"]}]
        wishes = [{"id": "w1", "name": "Libro", "details": "Tapa dura", "url": "",
                   "favorite": True, "purchased": True, "delivery_date": "SECRETO",
                   "private": {"gifts": "SECRETO"}}]
        before = copy.deepcopy((history, wishes))
        payload = build_public_payload(history, wishes)
        self.assertNotIn("SECRETO", json.dumps(payload))
        self.assertEqual(set(payload["wishes"][0]), {"id", "name", "details", "url", "favorite"})
        self.assertEqual((history, wishes), before)
        self.assertEqual(len(payload["conversation"]), 2)

    def test_non_string_fields_do_not_serialize_nested_private_data(self):
        payload = build_public_payload(
            [{"role": "user", "content": {"private": "SECRETO"}}],
            [{"id": "w1", "name": "Libro", "details": {"private": "SECRETO"}}],
        )
        self.assertNotIn("SECRETO", json.dumps(payload))
        self.assertEqual(payload["conversation"], [])

    def test_anticipation_accepts_only_a_literal_permission_bit(self):
        payload = build_public_payload([], [], {"visit_active": True,
            "gifts": "PRIVATE-GIFT", "delivery_at": "PRIVATE-DATE", "clues": ["UNSENT-CLUE"]})
        self.assertEqual(payload["mystery"], {"visit_active": True, "arrival_near": False})
        self.assertNotIn("PRIVATE", json.dumps(payload))
        self.assertNotIn("UNSENT", json.dumps(payload))
        for context in [None, True, [True], {"visit_active": 1}, {"visit_active": "true"}]:
            with self.subTest(context=context):
                self.assertEqual(build_public_payload([], [], context)["mystery"], {"visit_active": False, "arrival_near": False})

    def test_nearness_requires_active_visit_and_literal_boolean(self):
        for active, near, expected in [(True, True, True), (False, True, False),
                                        (True, "true", False), (True, 1, False)]:
            with self.subTest(active=active, near=near):
                payload = build_public_payload([], [], {"visit_active": active, "arrival_near": near})
                self.assertEqual(payload["mystery"], {"visit_active": active, "arrival_near": expected})

    def test_cow_voice_is_idempotent_and_preserves_urls_and_other_words(self):
        text = "Muy bien, mucha leche y muchísimas ganas. Muuuuuy feliz. Mundo música. https://mucho.example/muy?q=mucha www.muy.es"
        changed = cow_voice(text)
        self.assertIn("Muuuuy", changed)
        self.assertIn("muuuucha leche", changed)
        self.assertIn("muuuuchísimas", changed)
        self.assertIn("Muuuuuy feliz", changed)
        self.assertIn("Mundo música", changed)
        self.assertIn("https://mucho.example/muy?q=mucha www.muy.es", changed)
        self.assertEqual(cow_voice(changed), changed)


class GenerationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.history = [{"role": "user", "content": "Quiero unas zapatillas rosas del 38"}]
        self.wishes = [{"id": "w1", "name": "Libro", "details": "", "url": "", "favorite": False}]
        self.create = AsyncMock()
        client = SimpleNamespace(responses=SimpleNamespace(create=self.create))
        self.factory = patch("vaca_service.AsyncOpenAI")
        self.mock_factory = self.factory.start()
        self.mock_factory.return_value.__aenter__ = AsyncMock(return_value=client)
        self.mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        self.env = patch.dict("os.environ", {"OPENAI_API_KEY": "test-key", "VACA_MODEL": "test-model"})
        self.env.start()
        self.addCleanup(self.factory.stop)
        self.addCleanup(self.env.stop)

    def response(self, data, **overrides):
        value = {"output_text": json.dumps(data), "status": "completed", "output": []}
        value.update(overrides)
        self.create.return_value = SimpleNamespace(**value)

    async def test_strict_schema_no_storage_and_only_public_payload(self):
        self.response(reply(operations=[operation()]))
        self.wishes[0]["delivery_date"] = "PRIVATE-DATE"
        result = await generate_vaca_reply(self.history, self.wishes)
        self.assertEqual(result["operations"], [operation()])
        self.assertIn("muuuucha", result["reply"])
        kwargs = self.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "test-model")
        self.assertIs(kwargs["store"], False)
        self.assertIs(kwargs["text"]["format"]["strict"], True)
        self.assertEqual(kwargs["text"]["format"]["type"], "json_schema")
        self.assertNotIn("PRIVATE-DATE", kwargs["input"])
        self.assertEqual(self.mock_factory.call_args.kwargs["max_retries"], 1)
        self.assertEqual(self.mock_factory.call_args.kwargs["timeout"], 40)

    async def test_current_batched_user_messages_can_authorize_operation(self):
        self.history.extend([{"role": "user", "content": "Y el libro es mi favorito"}])
        self.response(reply(operations=[operation(), operation(action="update", id="w1", name="Libro",
                              details="", url="", favorite=True, evidence="Y el libro es mi favorito")]))
        result = await generate_vaca_reply(self.history, self.wishes)
        self.assertEqual(len(result["operations"]), 2)

    async def test_chat_anticipation_uses_public_conversation_and_no_private_plan_fields(self):
        self.response(reply(reply="Mi campanilla guarda un secreto de pezuña, Patita."))
        history = [{"role": "assistant", "content": "Pista ya recibida: las estrellas esconden un lazo."},
                   {"role": "user", "content": "¿Me susurras una profecía?"}]
        result = await generate_vaca_reply(history, self.wishes,
            {"visit_active": True, "gifts": "SECRET PURCHASE", "next_clue": "SECRET FUTURE CLUE"})
        payload = json.loads(self.create.call_args.kwargs["input"])
        self.assertEqual(payload["mystery"], {"visit_active": True, "arrival_near": False})
        self.assertIn("Pista ya recibida", payload["conversation"][0]["content"])
        self.assertNotIn("SECRET", self.create.call_args.kwargs["input"])
        self.assertEqual(result["operations"], [])
        self.assertIs(self.create.call_args.kwargs["store"], False)

    async def test_old_user_or_assistant_evidence_cannot_mutate(self):
        self.history += [{"role": "assistant", "content": "Quiero unas zapatillas rosas del 38"},
                         {"role": "user", "content": "Hola"}]
        self.response(reply(operations=[operation()]))
        with self.assertRaises(VacaGenerationError):
            await generate_vaca_reply(self.history, self.wishes)

    async def test_invalid_operations_fail_whole_result(self):
        for bad in [operation(action="update", id="missing"),
                    operation(favorite="true"), operation(url="javascript:alert(1)"),
                    operation(evidence="a fabricated quote"), operation(action="erase_all")]:
            with self.subTest(bad=bad):
                self.response(reply(operations=[operation(), bad]))
                with self.assertRaises(VacaGenerationError):
                    await generate_vaca_reply(self.history, self.wishes)

    async def test_new_generated_wish_names_and_details_cannot_carry_technical_prose(self):
        original = copy.deepcopy((self.history, self.wishes))
        for action in ('add', 'update'):
            for field in ('name', 'details'):
                with self.subTest(action=action, field=field):
                    bad = operation(action=action, id='w1' if action == 'update' else '',
                                    **{field:'Soy un bot de Telegram'})
                    self.response(reply(operations=[bad], show_list=True))
                    with self.assertRaises(VacaGenerationError):
                        await generate_vaca_reply(self.history, self.wishes)
                    self.assertEqual((self.history, self.wishes), original)

    async def test_existing_wish_text_is_not_rewritten_or_rejected_when_unchanged(self):
        self.wishes[0].update(name='Robot de juguete', details='Texto antiguo de Sandra: Telegram')
        self.history = [{'role':'user', 'content':'Marca el libro como favorito'}]
        unchanged = operation(action='update', id='w1', name=self.wishes[0]['name'],
            details=self.wishes[0]['details'], url='', favorite=True, evidence='Marca el libro como favorito')
        self.response(reply(operations=[unchanged]))
        result = await generate_vaca_reply(self.history, self.wishes)
        self.assertEqual(result['operations'], [unchanged])
        self.assertEqual(self.wishes[0]['details'], 'Texto antiguo de Sandra: Telegram')

    async def test_refusal_incomplete_and_malformed_output_are_safe(self):
        for overrides in [{"status": "incomplete"}, {"output_text": "not json"},
                          {"output": [{"content": [{"type": "refusal", "refusal": "PRIVATE"}]}]}]:
            self.response(reply(), **overrides)
            with self.assertRaises(VacaGenerationError) as caught:
                await generate_vaca_reply(self.history, self.wishes)
            self.assertNotIn("PRIVATE", str(caught.exception))

    async def test_api_error_does_not_log_inputs_or_credentials(self):
        self.create.side_effect = RuntimeError("PRIVATE-GIFT test-key")
        with self.assertLogs("control-castora.vaca", level="WARNING") as logs:
            with self.assertRaises(VacaGenerationError) as caught:
                await generate_vaca_reply(self.history, self.wishes)
        text = " ".join(logs.output) + str(caught.exception)
        self.assertNotIn("PRIVATE-GIFT", text)
        self.assertNotIn("test-key", text)

    async def test_missing_key_does_not_call_api(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": ""}):
            with self.assertRaises(VacaGenerationError):
                await generate_vaca_reply(self.history, self.wishes)
        self.create.assert_not_awaited()

    async def test_visit_generation_is_isolated_and_cow_voice_applies(self):
        self.response({"clues": ["Algo suave me tiene muy entretenida.", "Un lazo se ha escapado."],
                       "morning": "Buenos días, patita. He dejado mucho cariño bajo el árbol."})
        result = await generate_visit_messages("Regalo privado: bufanda")
        payload = json.loads(self.create.call_args.kwargs["input"])
        self.assertEqual(payload, {"gifts": "Regalo privado: bufanda"})
        self.assertNotIn("conversation", payload)
        self.assertIn("muuuucho", result["morning"])
        self.assertEqual(len(result["clues"]), 2)

    async def test_visit_drafts_reject_obvious_dates_links_and_oversize(self):
        for bad in ["El 24 voy", "Mira https://regalo.example", "x" * 901]:
            self.response({"clues": [bad, "Un lazo se ha escapado."], "morning": "Buenos días, patita."})
            with self.assertRaises(VacaGenerationError):
                await generate_visit_messages("Un regalo")


if __name__ == "__main__":
    unittest.main()
