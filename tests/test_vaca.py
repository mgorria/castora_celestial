import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from vaca import HELP, MAX_WISHES, UNAVAILABLE_TEXT, WELCOME, WELCOME_BACK, Vaca
from vaca_service import cow_voice


def update(text="hola", user_id=1, chat_type="private", chat_id=None):
    return SimpleNamespace(
        effective_chat=SimpleNamespace(id=user_id if chat_id is None else chat_id, type=chat_type),
        effective_user=SimpleNamespace(id=user_id), message=SimpleNamespace(text=text),
    )


def operation(action="add", identity="", name="Zapatillas rosas", evidence="quiero zapatillas", **fields):
    result = {"action": action, "id": identity, "name": name, "details": "talla 38",
              "url": "", "favorite": False, "evidence": evidence}
    result.update(fields)
    return result


def answer(reply="Me hace mucha ilusión, patita.", operations=None, show_list=False):
    return {"reply": reply, "operations": operations or [], "show_list": show_list}


class VacaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"private_gifts": [{"name": "SECRETO", "date": "2030-12-05"}]}
        self.allowed = {1, 2}
        self.send = AsyncMock()
        self.notify = AsyncMock()

        def save(data):
            self.data = copy.deepcopy(data)

        self.bot = Vaca(lambda: copy.deepcopy(self.data), save, lambda: self.allowed,
                        self.send, self.notify, idle_seconds=1)
        self.bot.idle_seconds = 0.001

    async def asyncTearDown(self):
        await self.bot.close()

    async def finish(self):
        await asyncio.wait_for(asyncio.gather(*list(self.bot.tasks.values())), timeout=2)

    async def test_private_authorized_chats_only(self):
        original = copy.deepcopy(self.data)
        for incoming in [update(user_id=99), update(chat_type="group"),
                         update(chat_type="supergroup"), update(user_id=1, chat_id=2)]:
            await self.bot.receive(incoming, None)
            await self.bot.welcome(incoming, None)
        self.assertEqual(self.data, original)
        self.send.assert_not_awaited()

    async def test_first_start_is_narrative_and_persists_only_after_delivery(self):
        observations = []

        async def send(chat_id, text):
            observations.append((self.bot.session(chat_id), text))

        self.bot.send = send
        with patch("vaca.generate_vaca_reply", AsyncMock()) as generate:
            await self.bot.welcome(update("/start"), None)
        generate.assert_not_awaited()
        self.assertIsNone(observations[0][0])
        self.assertEqual(observations[0][1], cow_voice(WELCOME))
        self.assertLessEqual(len(observations[0][1].split()), 80)
        self.assertNotIn("/pedir", observations[0][1])
        self.assertIn("muuu", observations[0][1])
        self.assertTrue(self.bot.session(1)["welcomed"])
        self.assertEqual(self.bot.session(1)["history"], [
            {"role": "assistant", "content": cow_voice(WELCOME)},
        ])

    async def test_repeated_start_is_short_and_preserves_existing_wishes(self):
        await self.bot.receive(update("/pedir libro"), None)
        original_wishes = copy.deepcopy(self.bot.session(1)["wishes"])
        await self.bot.receive(update("/start"), None)
        self.assertEqual(self.send.call_args.args[1], cow_voice(WELCOME))
        await self.bot.receive(update("/start"), None)
        self.assertEqual(self.send.call_args.args[1], cow_voice(WELCOME_BACK))
        self.assertLess(len(self.send.call_args.args[1]), len(WELCOME))
        self.assertEqual(self.bot.session(1)["wishes"], original_wishes)
        self.assertEqual(self.bot.session(1)["history"][-1]["content"], cow_voice(WELCOME_BACK))

    async def test_failed_welcome_never_marks_welcomed_or_adds_history(self):
        await self.bot.receive(update("/pedir libro"), None)
        original_session = self.bot.session(1)
        self.send.side_effect = TimeoutError()
        await self.bot.welcome(update("/start"), None)
        self.assertEqual(self.bot.session(1), original_session)
        self.assertNotIn("welcomed", self.bot.session(1))
        self.send.side_effect = None
        await self.bot.welcome(update("/start"), None)
        self.assertEqual(self.send.call_args.args[1], cow_voice(WELCOME))
        self.assertTrue(self.bot.session(1)["welcomed"])

    async def test_help_keeps_commands_without_marking_welcomed(self):
        await self.bot.receive(update("/ayuda"), None)
        self.send.assert_awaited_once_with(1, cow_voice(HELP))
        self.assertIn("El Oso", self.send.call_args.args[1])
        self.assertIsNone(self.bot.session(1))

    async def test_commands_work_without_model_and_keep_each_list_separate(self):
        with patch("vaca.generate_vaca_reply", AsyncMock()) as generate:
            await self.bot.receive(update("/pedir Mucho amor https://example.com/mucho"), None)
            await self.bot.receive(update("/pedir libro", user_id=2), None)
            await self.bot.receive(update("/favorito w1"), None)
            await self.bot.receive(update("/lista"), None)
        generate.assert_not_awaited()
        self.assertEqual(self.bot.session(1)["wishes"][0]["name"], "Mucho amor")
        self.assertEqual(self.bot.session(1)["wishes"][0]["url"], "https://example.com/mucho")
        self.assertTrue(self.bot.session(1)["wishes"][0]["favorite"])
        self.assertEqual(self.bot.session(2)["wishes"][0]["name"], "libro")
        self.assertNotIn("libro", self.send.call_args.args[1])
        self.assertNotIn("SECRETO", str(self.send.call_args_list))

    async def test_deterministic_duplicate_does_not_add_twice_and_ids_not_reused(self):
        await self.bot.receive(update("/pedir libro"), None)
        await self.bot.receive(update("/pedir Libro"), None)
        self.assertEqual(len(self.bot.session(1)["wishes"]), 1)
        await self.bot.receive(update("/quitar w1"), None)
        await self.bot.receive(update("/pedir perfume"), None)
        self.assertEqual(self.bot.session(1)["wishes"][0]["id"], "w2")

    async def test_batching_and_confirmations_only_after_saved_changes(self):
        observations = []

        async def send(chat_id, text):
            observations.append((copy.deepcopy(self.data), text))

        self.bot.send = send
        model = AsyncMock(return_value=answer(operations=[operation()]))
        with patch("vaca.generate_vaca_reply", model):
            await self.bot.receive(update("quiero zapatillas"), None)
            await self.bot.receive(update("rosas del 38"), None)
            await self.finish()
        model.assert_awaited_once()
        self.assertEqual(len(model.call_args.args[0]), 2)
        self.assertNotIn("SECRETO", str(model.call_args))
        self.assertEqual(observations[0][0]["vaca"]["sessions"]["1"]["wishes"][0]["name"], "Zapatillas rosas")
        self.assertIn("Apuntado: w1. Zapatillas rosas", observations[0][1])
        self.assertIn("muuu", observations[0][1])
        self.notify.assert_awaited_once()
        self.assertFalse(self.bot.session(1)["pending"])

    async def test_casual_admiration_no_list_change_when_service_returns_none(self):
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer("¿Quieres que lo apunte?"))):
            await self.bot.receive(update("qué bonito este libro"), None)
            await self.finish()
        self.assertEqual(self.bot.session(1)["wishes"], [])
        self.notify.assert_not_awaited()

    async def test_invalid_operation_batch_is_atomic(self):
        good = operation()
        bad = operation(action="remove", identity="w999", name="", evidence="quiero zapatillas")
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer(operations=[good, bad]))):
            await self.bot.receive(update("quiero zapatillas"), None)
            await self.finish()
        self.assertEqual(self.bot.session(1)["wishes"], [])
        self.assertEqual(self.bot.session(1)["next_wish_id"], 1)
        self.send.assert_awaited_once_with(1, UNAVAILABLE_TEXT)
        self.notify.assert_not_awaited()

    async def test_evidence_must_come_from_current_pending_messages(self):
        session = self.bot.new_session()
        session["history"] = [{"role": "user", "content": "quiero zapatillas"},
                              {"role": "assistant", "content": "¿De qué color?"}]
        self.bot.set_session(1, session)
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer(operations=[operation()]))):
            await self.bot.receive(update("hoy no quiero apuntar nada"), None)
            await self.finish()
        self.assertFalse(self.bot.session(1)["wishes"])
        self.send.assert_awaited_once_with(1, UNAVAILABLE_TEXT)

    async def test_malformed_fields_and_unsafe_url_are_rejected(self):
        for fields in [{"favorite": "yes"}, {"name": "a" * 241},
                       {"url": "file:///secret"}, {"id": "invented"},
                       {"evidence": ""}]:
            with self.subTest(fields=fields):
                session = self.bot.new_session()
                with self.assertRaises(ValueError):
                    self.bot._apply_operations(session, [operation(**fields)], "quiero zapatillas")

    async def test_list_can_be_shown_after_natural_mutation(self):
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer(operations=[operation()], show_list=True))):
            await self.bot.receive(update("quiero zapatillas y ver mi lista"), None)
            await self.finish()
        self.assertIn("Cuaderno de ilusiones", self.send.call_args.args[1])
        self.assertIn("Zapatillas rosas", self.send.call_args.args[1])

    async def test_new_input_discards_obsolete_generation(self):
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def generate(history, wishes, anticipation):
            calls.append(copy.deepcopy(history))
            if len(calls) == 1:
                started.set()
                await release.wait()
                return answer("Obsoleto", [operation()])
            return answer("Entonces no lo apunto.")

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            await self.bot.receive(update("espera, mejor no"), None)
            release.set()
            await self.finish()
        self.send.assert_awaited_once_with(1, "Entonces no lo apunto.")
        self.assertFalse(self.bot.session(1)["wishes"])

    async def test_remove_during_generation_cannot_resurrect_wish(self):
        await self.bot.receive(update("/pedir zapatillas"), None)
        self.send.reset_mock()
        started = asyncio.Event()
        release = asyncio.Event()

        async def generate(*args):
            started.set()
            await release.wait()
            return answer(operations=[operation(action="update", identity="w1", evidence="mejor rosas")])

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("mejor rosas"), None)
            await asyncio.wait_for(started.wait(), 1)
            await self.bot.receive(update("/quitar w1"), None)
            release.set()
            await self.finish()
        self.assertFalse(self.bot.session(1)["wishes"])
        self.send.assert_awaited_once()
        self.assertIn("Quitado", self.send.call_args.args[1])

    async def test_public_clue_during_generation_preserves_pending_request(self):
        started = asyncio.Event()
        release = asyncio.Event()
        calls = []

        async def generate(history, wishes, anticipation):
            calls.append(copy.deepcopy(history))
            if len(calls) == 1:
                started.set()
                await release.wait()
                return answer("Obsoleto")
            return answer("¡Qué ilusión!", [operation()])

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            self.bot.remember_outgoing(1, "Una pista: algo calentito.")
            release.set()
            await self.finish()
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][-1], {"role": "user", "content": "quiero zapatillas"})
        self.assertEqual(calls[1][-2]["content"], "Una pista: algo calentito.")
        self.assertEqual(len(self.bot.session(1)["wishes"]), 1)
        self.assertNotIn("Obsoleto", str(self.send.call_args_list))

    def active_visit(self):
        plan = {"status": "active", "recipient_id": 1, "delivery_at": "2099-12-20T08:00:00+01:00",
                "gifts": "SECRET PURCHASE", "events": {
                    "pista1": {"status": "sent", "text": "FORGOTTEN DELIVERED CLUE"},
                    "pista2": {"status": "pending", "text": "SECRET FUTURE CLUE"},
                    "manana": {"status": "pending", "text": "SECRET MORNING"}}}
        self.data["vaca_campaigns"] = {"paused": False, "plans": {"PRIVATE-ID": plan}}

    async def test_active_visit_passes_only_permission_and_never_recovers_forgotten_clues(self):
        self.active_visit()
        self.bot.remember_outgoing(1, "FORGOTTEN DELIVERED CLUE")
        await self.bot.receive(update("/olvidar"), None)
        self.send.reset_mock()
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer("Una profecía de pezuña."))) as model:
            await self.bot.receive(update("¿Me susurras una profecía?"), None)
            await self.finish()
        history, wishes, anticipation = model.call_args.args
        self.assertEqual(anticipation, {"visit_active": True, "arrival_near": False})
        self.assertNotIn("SECRET", str(model.call_args))
        self.assertNotIn("PRIVATE-ID", str(model.call_args))
        self.assertNotIn("FORGOTTEN", str(history))
        self.assertFalse(wishes)
        self.notify.assert_not_awaited()

    async def test_cancelling_visit_during_generation_discards_anticipation(self):
        self.active_visit()
        started, release = asyncio.Event(), asyncio.Event()
        permissions = []

        async def generate(history, wishes, anticipation):
            permissions.append(copy.deepcopy(anticipation))
            if len(permissions) == 1:
                started.set()
                await release.wait()
                return answer("OUTDATED ANTICIPATION")
            return answer("La campanilla propone un juego de palabras, Patita.")

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("¿Qué dice tu campanilla?"), None)
            await asyncio.wait_for(started.wait(), 1)
            self.data["vaca_campaigns"]["plans"]["PRIVATE-ID"]["status"] = "cancelled"
            release.set()
            await self.finish()
        self.assertEqual(permissions, [{"visit_active": True, "arrival_near": False}, {"visit_active": False, "arrival_near": False}])
        self.send.assert_awaited_once_with(1, "La campanilla propone un juego de palabras, Patita.")
        self.assertNotIn("OUTDATED", str(self.send.call_args_list))

    async def test_forget_clears_memory_preserves_list_and_discards_generation(self):
        await self.bot.receive(update("/pedir libro"), None)
        self.send.reset_mock()
        started = asyncio.Event()
        release = asyncio.Event()

        async def generate(*args):
            started.set()
            await release.wait()
            return answer("Obsoleto")

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            await self.bot.receive(update("/olvidar"), None)
            release.set()
            await self.finish()
        self.assertEqual(self.bot.session(1)["history"], [])
        self.assertEqual(self.bot.session(1)["wishes"][0]["name"], "libro")
        self.send.assert_awaited_once()

    async def test_generation_failure_consumes_batch_without_loop(self):
        with patch("vaca.generate_vaca_reply", AsyncMock(side_effect=ValueError("secret data"))) as generate:
            await self.bot.receive(update("quiero zapatillas"), None)
            await self.finish()
            self.bot.maintenance()
            await self.finish()
        generate.assert_awaited_once()
        self.send.assert_awaited_once_with(1, UNAVAILABLE_TEXT)
        self.assertFalse(self.bot.session(1)["pending"])

    async def test_uncertain_delivery_does_not_repeat_mutation_or_send(self):
        self.send.side_effect = TimeoutError()
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer(operations=[operation()]))) as generate:
            await self.bot.receive(update("quiero zapatillas"), None)
            await self.finish()
            self.bot.maintenance()
            await self.finish()
        generate.assert_awaited_once()
        self.send.assert_awaited_once()
        self.assertEqual(len(self.bot.session(1)["wishes"]), 1)
        self.assertFalse(self.bot.session(1)["pending"])

    async def test_pending_batch_survives_restart(self):
        self.bot.idle_seconds = 100
        await self.bot.receive(update("quiero zapatillas"), None)
        await self.bot.close()
        session = self.bot.session(1)
        session["due_at"] = time.time() - 1
        self.bot.set_session(1, session)
        with patch("vaca.generate_vaca_reply", AsyncMock(return_value=answer(operations=[operation()]))):
            self.bot.maintenance()
            await self.finish()
        self.assertEqual(len(self.bot.session(1)["wishes"]), 1)
        self.send.assert_awaited_once()

    async def test_disabled_chat_still_has_deterministic_list_commands(self):
        self.bot.set_enabled(False)
        with patch("vaca.generate_vaca_reply", AsyncMock()) as generate:
            await self.bot.receive(update("hola"), None)
            await self.bot.receive(update("/pedir libro"), None)
            await self.bot.receive(update("/lista"), None)
        generate.assert_not_awaited()
        self.assertEqual(self.bot.session(1)["wishes"][0]["name"], "libro")

    async def test_turning_off_invalidates_and_cancels_pending_generation(self):
        started = asyncio.Event()

        async def generate(*args):
            started.set()
            await asyncio.Event().wait()

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            tasks = list(self.bot.tasks.values())
            self.bot.set_enabled(False)
            await asyncio.gather(*tasks, return_exceptions=True)
            self.bot.set_enabled(True)
            self.bot.maintenance()
        self.send.assert_not_awaited()
        self.assertFalse(self.bot.session(1)["pending"])

    async def test_save_failure_does_not_claim_success_or_mutate_memory(self):
        original = copy.deepcopy(self.data)
        self.bot.save = lambda data: (_ for _ in ()).throw(OSError("disk unavailable"))
        await self.bot.receive(update("/pedir libro"), None)
        self.assertEqual(self.data, original)
        self.assertIn("No he podido guardar", self.send.call_args.args[1])
        self.assertNotIn("Apuntado", self.send.call_args.args[1])
        self.notify.assert_not_awaited()

    async def test_worker_storage_failure_does_not_repeat_api_calls(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def generate(*args):
            started.set()
            await release.wait()
            return answer(operations=[operation()])

        with patch("vaca.generate_vaca_reply", AsyncMock(side_effect=generate)) as model:
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            self.bot.save = lambda data: (_ for _ in ()).throw(OSError("disk unavailable"))
            release.set()
            await self.finish()
            self.bot.maintenance()
            await self.finish()
        model.assert_awaited_once()
        self.assertFalse(self.bot.session(1)["wishes"])
        self.assertNotIn("Apuntado", self.send.call_args.args[1])

    async def test_authorization_revoked_during_generation_prevents_send_and_mutation(self):
        started = asyncio.Event()
        release = asyncio.Event()

        async def generate(*args):
            started.set()
            await release.wait()
            return answer(operations=[operation()])

        with patch("vaca.generate_vaca_reply", generate):
            await self.bot.receive(update("quiero zapatillas"), None)
            await asyncio.wait_for(started.wait(), 1)
            self.allowed.remove(1)
            release.set()
            await self.finish()
        self.send.assert_not_awaited()
        self.assertFalse(self.bot.session(1)["wishes"])

    async def test_wishlist_is_bounded(self):
        session = self.bot.new_session()
        for number in range(MAX_WISHES):
            self.bot._new_wish(session, f"Regalo {number}")
        self.bot.set_session(1, session)
        await self.bot.receive(update("/pedir uno más"), None)
        self.assertEqual(len(self.bot.session(1)["wishes"]), MAX_WISHES)
        self.assertIn("60 deseos", self.send.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
