import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from salchicher import CONSULTATION_GREETING, INACTIVITY_SECONDS, RETENTION_SECONDS, Salchicher
from salchicher_service import CARE, EMERGENCY_TEXT
from salchicher_copy import LEGACY_GREETING, LEGACY_INTRO, LEGACY_QUESTIONS


def incoming(text, user_id=1):
    chat = SimpleNamespace(id=user_id, type="private", send_message=AsyncMock())
    return SimpleNamespace(effective_chat=chat, effective_user=SimpleNamespace(id=user_id),
                           message=SimpleNamespace(text=text), callback_query=None)


class ConsultationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.data = {"unrelated": {"keep": True}}
        self.send = AsyncMock()
        self.notify = AsyncMock()
        self.bot = self.new_bot()

    def new_bot(self):
        def save(data):
            self.data = copy.deepcopy(data)
        bot = Salchicher(lambda: copy.deepcopy(self.data), save, lambda: {1, 2},
                         self.send, self.notify, idle_seconds=1)
        bot.idle_seconds = 0
        return bot

    async def asyncTearDown(self):
        await self.bot.close()

    async def finish(self):
        await asyncio.wait_for(asyncio.gather(*list(self.bot.tasks.values())), timeout=2)

    async def test_headache_alone_keeps_the_consultation_open(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        response = "Me ajusto las gafitas, Patita. ¿Desde cuándo te molesta la cabecita?"
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=(response, ["head_duration"]))) as provider:
            await self.bot.receive(incoming("Me duele mucho la cabeza"), None)
            await self.finish()
        provider.assert_awaited_once()
        current = self.bot.get_consultation(1, episode["id"])
        self.assertEqual(current["status"], "active")
        self.assertIsNone(current["closure_reason"])
        self.assertEqual(current["messages"][-1]["content"], response)
        self.assertNotIn("112", current["messages"][-1]["content"])

    async def test_retired_automatic_copy_is_only_projected_out_of_saved_or_temporary_history(self):
        screening = "Gracias por contármelo, solete. " + LEGACY_QUESTIONS["duration"] + "\n\n" + LEGACY_QUESTIONS["context"]
        messages = [{"role": "assistant", "content": text, "created_at": time.time()}
                    for text in (LEGACY_GREETING, LEGACY_INTRO, screening)] + [
            {"role": "user", "content": screening, "created_at": time.time()},
            {"role": "assistant", "content": "Nota manual: " + screening, "created_at": time.time()},
            {"role": "assistant", "content": "Te dejo una mantita.", "created_at": time.time()},
        ]
        for retained in (True, False):
            with self.subTest(retained=retained):
                self.bot.forget(1)
                episode = self.bot.start_consultation(1, retain_history=retained)
                state = self.data["salchicher"]
                stored = (state["consultations"]["1"][episode["id"]] if retained
                          else state["sessions"]["1"]["consultation"])
                stored["messages"] = copy.deepcopy(messages)
                before = copy.deepcopy(self.data)
                projected = self.bot.get_consultation(1, episode["id"])
                self.assertEqual(projected["messages"], messages[3:])
                self.assertEqual(self.data, before)
                projected["messages"][-1]["content"] = "Changed output only"
                self.assertEqual(self.data, before)

    async def test_manual_delivery_stays_in_the_episode_that_was_open_when_sent(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        self.bot.record_manual_delivery(1, "Te he dejado una mantita, patita.", episode["id"])
        stored = self.bot.get_consultation(1, episode["id"])
        self.assertEqual(stored["messages"][-1]["content"], "Te he dejado una mantita, patita.")
        self.assertEqual(stored["messages"][-1]["role"], "assistant")
        self.bot.close_consultation(1, episode["id"])
        next_episode = self.bot.start_consultation(1, retain_history=True)
        self.bot.record_manual_delivery(1, "Respuesta tardía", episode["id"])
        self.assertEqual(len(self.bot.get_consultation(1, next_episode["id"])["messages"]), 1)
        self.send.assert_not_awaited()

    async def test_next_visit_varies_greeting_with_style_ids_only_and_forget_resets_them(self):
        from salchicher_vademecum import render_storybook
        first = self.bot.start_consultation(1, retain_history=False)
        session = self.bot.session(1)
        self.bot._save_message(1, session, "user", "SINTOMA_PRIVADO: me duele la cabecita desde ayer")
        recipe = render_storybook({"diagnosis": "busy_head", "care": ["food"],
                                   "presentation": "recipe", "opening": "stamp", "closing": "paw"})
        self.bot._save_message(1, self.bot.session(1), "assistant", recipe)
        self.bot.close_consultation(1, first["id"])
        serialized = str(self.data)
        self.assertNotIn("SINTOMA_PRIVADO", serialized)
        self.assertNotIn("busy_head", serialized)
        self.assertNotIn(CARE["food"], serialized)
        self.assertTrue(self.bot.state()["voice_memory"]["1"])
        await self.bot.close()
        self.bot = self.new_bot()
        second = self.bot.start_consultation(1, retain_history=False)
        self.assertNotEqual(first["messages"][0]["content"], second["messages"][0]["content"])
        self.assertNotIn("gafitas", second["messages"][0]["content"])
        self.assertNotIn("SINTOMA_PRIVADO", str(self.bot._style_history(1)))
        self.bot.forget(1)
        self.assertNotIn("1", self.bot.state().get("voice_memory", {}))
        third = self.bot.start_consultation(1, retain_history=False)
        self.assertEqual(third["messages"][0]["content"], first["messages"][0]["content"])

    async def test_user_quotes_never_update_cross_visit_style_and_memory_stays_bounded(self):
        from salchicher_copy import REPLIES
        self.bot.start_consultation(1, retain_history=True)
        before = copy.deepcopy(self.bot.state()["voice_memory"])
        self.bot._save_message(1, self.bot.session(1), "user", REPLIES["thanks"]["welcome"])
        self.assertEqual(self.bot.state()["voice_memory"], before)
        for index in range(30):
            self.bot._save_message(1, self.bot.session(1), "assistant", REPLIES["thanks"]["welcome"])
        self.assertLessEqual(len(self.bot.state()["voice_memory"]["1"]), 24)
        self.assertTrue(all(isinstance(value, str) for value in self.bot.state()["voice_memory"]["1"]))

    async def test_answered_facts_remain_in_this_episode_after_context_rolls_over(self):
        self.bot.start_consultation(1, retain_history=True)
        self.bot._save_message(1, self.bot.session(1), "user", "Me duele la cabecita desde ayer; hoy sigue igual")
        for index in range(30):
            self.bot._save_message(1, self.bot.session(1), "assistant", f"Mensaje de compañía {index}")
        self.assertNotIn("desde ayer", str(self.bot.session(1)["history"]))
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("Sigo aquí.", []))) as provider:
            await self.bot.receive(incoming("Otro poquito de compañía"), None)
            await self.finish()
        blocked = provider.call_args.args[1]
        self.assertTrue({"duration", "head_duration", "symptoms", "evolution"}.issubset(blocked))
        self.bot.close_consultation(1, self.bot.active_consultation(1)["id"])
        self.bot.start_consultation(1, retain_history=True)
        self.assertEqual(self.bot.session(1).get("answered", []), [])

    async def test_explicit_history_choice_and_private_by_default(self):
        for choice in (None, 0, 1, "true", "false"):
            with self.subTest(choice=choice), self.assertRaisesRegex(ValueError, "consent_required"):
                self.bot.start_consultation(1, retain_history=choice)
        self.assertEqual(self.bot.list_consultations(1), [])
        episode = self.bot.start_consultation(1, retain_history=True)
        self.assertTrue(episode["retained"])
        self.assertEqual(episode["messages"][0]["content"], CONSULTATION_GREETING)
        self.assertFalse(self.bot.session(1)["shared"])
        self.send.assert_not_awaited()
        self.notify.assert_not_awaited()
        with self.assertRaisesRegex(ValueError, "consultation_active"):
            self.bot.start_consultation(1, retain_history=True)

    async def test_help_stays_in_story_without_sharing_or_clinical_notices(self):
        for retained in (True, False):
            with self.subTest(retained=retained):
                self.bot.forget(1)
                self.bot.start_consultation(1, retain_history=retained)
                update = incoming("/ayuda")
                await self.bot.welcome(update, None)
                sent = update.effective_chat.send_message.call_args
                text = sent.args[0]
                self.assertNotIn("reply_markup", sent.kwargs)
                self.assertIn("Patita", text)
                self.assertNotIn("¿", text, "Returning to help does not repeat the intake question")
                for forbidden in ("compart", "copia", "privad", "Sandra", "Miguel", "embarazo", "profesional", "112"):
                    self.assertNotIn(forbidden, text)

    async def test_saved_episode_survives_restart_and_bounds_only_model_context(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=(CARE["comfort"], []))):
            for index in range(30):
                await self.bot.receive(incoming(f"Mensaje de prueba {index}"), None)
            await self.finish()
        self.assertEqual(len(self.bot.session(1)["history"]), 24)
        await self.bot.close()
        self.bot = self.new_bot()
        restored = self.bot.get_consultation(1, episode["id"])
        self.assertEqual(len(restored["messages"]), 32)
        self.assertEqual(restored["messages"][1]["content"], "Mensaje de prueba 0")
        self.assertEqual(restored["care_summary"], [CARE["comfort"]])
        self.assertEqual(self.bot.active_consultation(1)["id"], episode["id"])
        self.assertTrue(self.data["unrelated"]["keep"])
        self.notify.assert_not_awaited()

    async def test_user_report_closes_episode_without_medical_conclusion(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        result = self.bot.close_consultation(1, episode["id"])
        self.assertEqual(result["status"], "recovered")
        self.assertEqual(result["closure_reason"], "feeling_better")
        self.assertIsNone(self.bot.active_consultation(1))
        self.assertEqual(result["care_summary"], [])
        self.assertNotIn("diagnosis", result)
        self.assertEqual(self.bot.get_consultation(1, episode["id"])["messages"], episode["messages"])

    async def test_thirty_day_inactivity_closes_never_recovers_and_reads_do_not_extend(self):
        start = time.time()
        with patch("salchicher.time.time", return_value=start):
            episode = self.bot.start_consultation(1, retain_history=True)
        with patch("salchicher.time.time", return_value=start + INACTIVITY_SECONDS - 1):
            self.assertEqual(self.bot.get_consultation(1, episode["id"])["status"], "active")
            self.assertEqual(self.bot.session(1)["updated_at"], start)
        with patch("salchicher.time.time", return_value=start + INACTIVITY_SECONDS):
            result = self.bot.get_consultation(1, episode["id"])
        self.assertEqual(result["status"], "inactive")
        self.assertEqual(result["closure_reason"], "inactivity")
        self.assertEqual(result["closed_at"], start + INACTIVITY_SECONDS)
        self.assertEqual(result["updated_at"], start)
        self.assertIsNone(self.bot.active_consultation(1))
        # Clicking an old "feeling better" control cannot rewrite an inactive record.
        self.assertEqual(self.bot.close_consultation(1, episode["id"])["status"], "inactive")

    async def test_unsaved_episode_erases_on_close_and_after_48_hours(self):
        episode = self.bot.start_consultation(1, retain_history=False)
        self.assertEqual(self.bot.list_consultations(1)[0]["id"], episode["id"])
        self.assertIsNone(self.bot.close_consultation(1, episode["id"]))
        self.assertIsNone(self.bot.get_consultation(1, episode["id"]))
        start = time.time()
        with patch("salchicher.time.time", return_value=start):
            episode = self.bot.start_consultation(1, retain_history=False)
        with patch("salchicher.time.time", return_value=start + RETENTION_SECONDS):
            self.assertEqual(self.bot.list_consultations(1), [])
        self.assertIsNone(self.bot.get_consultation(1, episode["id"]))
        self.assertNotIn(episode["id"], str(self.data))

    async def test_legacy_sessions_are_never_imported_or_granted_retention(self):
        self.bot.set_session(1, {
            "shared": True, "history": [{"role": "user", "content": "old private text"}],
            "asked": [], "updated_at": time.time(), "version": 1, "pending": False,
        })
        self.assertEqual(self.bot.list_consultations(1), [])
        self.assertIsNone(self.bot.active_consultation(1))
        episode = self.bot.start_consultation(1, retain_history=True)
        self.assertFalse(self.bot.session(1)["shared"])
        self.assertNotIn("old private text", str(self.data))
        self.assertEqual(len(episode["messages"]), 1)

    async def test_expiring_legacy_session_does_not_delete_saved_episodes(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        self.bot.close_consultation(1, episode["id"])
        self.bot.set_session(1, {"updated_at": time.time() - RETENTION_SECONDS, "pending": False})
        self.bot.maintenance()
        self.assertIsNone(self.bot.session(1))
        self.assertIsNotNone(self.bot.get_consultation(1, episode["id"]))

    async def test_archive_isolated_by_user_and_ids_are_not_cross_user_capabilities(self):
        one = self.bot.start_consultation(1, retain_history=True)
        two = self.bot.start_consultation(2, retain_history=True)
        self.assertIsNone(self.bot.get_consultation(2, one["id"]))
        self.assertFalse(self.bot.delete_consultation(2, one["id"]))
        self.assertIsNone(self.bot.close_consultation(2, one["id"]))
        self.assertEqual(self.bot.active_consultation(2)["id"], two["id"])
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.bot.list_consultations(3)
        with self.assertRaisesRegex(ValueError, "forbidden"):
            self.bot.start_consultation(3, retain_history=True)

    async def test_delete_and_forget_remove_archive_as_well_as_context(self):
        first = self.bot.start_consultation(1, retain_history=True)
        self.bot.close_consultation(1, first["id"])
        second = self.bot.start_consultation(1, retain_history=True)
        other = self.bot.start_consultation(2, retain_history=True)
        self.assertTrue(self.bot.delete_consultation(1, first["id"]))
        self.assertNotIn(first["id"], str(self.data))
        self.bot.forget(1)
        self.assertIsNone(self.bot.get_consultation(1, second["id"]))
        self.assertNotIn(second["id"], str(self.data))
        self.assertEqual(self.bot.active_consultation(2)["id"], other["id"])

    async def test_close_or_delete_during_generation_cannot_send_old_reply_or_recreate_archive(self):
        for action in ("close", "delete", "forget"):
            with self.subTest(action=action):
                self.bot.forget(1)
                first = self.bot.start_consultation(1, retain_history=True)
                started = asyncio.Event()
                release = asyncio.Event()

                async def generate(*args, **kwargs):
                    started.set()
                    await release.wait()
                    return "obsolete reply", []

                with patch("salchicher.generate_care_reply", generate):
                    await self.bot.receive(incoming("test"), None)
                    await asyncio.wait_for(started.wait(), timeout=1)
                    tasks = list(self.bot.tasks.values())
                    if action == "forget":
                        self.bot.forget(1)
                    else:
                        getattr(self.bot, f"{action}_consultation")(1, first["id"])
                    second = self.bot.start_consultation(1, retain_history=True)
                    release.set()
                    await asyncio.gather(*tasks, return_exceptions=True)
                self.send.assert_not_awaited()
                self.assertEqual(len(self.bot.get_consultation(1, second["id"])["messages"]), 1)
                self.assertNotIn("obsolete reply", str(self.data))

    async def test_late_transport_completion_does_not_attach_old_reply_to_new_consultation(self):
        first = self.bot.start_consultation(1, retain_history=True)
        sent = asyncio.Event()
        release = asyncio.Event()

        async def delayed_send(*args):
            sent.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        self.send.side_effect = delayed_send
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("old delivery", []))):
            await self.bot.receive(incoming("test"), None)
            await asyncio.wait_for(sent.wait(), timeout=1)
            tasks = list(self.bot.tasks.values())
            self.bot.delete_consultation(1, first["id"])
            second = self.bot.start_consultation(1, retain_history=True)
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(len(self.bot.get_consultation(1, second["id"])["messages"]), 1)
        self.assertNotIn(first["id"], str(self.data))
        self.assertNotIn("old delivery", str(self.data))

    async def test_late_legacy_delivery_cannot_revive_forgotten_health_text_in_new_session(self):
        def legacy(version):
            return {"shared": False, "history": [], "asked": [], "version": version,
                    "pending": False, "updated_at": time.time()}

        self.bot.set_session(1, legacy(1))
        sent = asyncio.Event()
        release = asyncio.Event()

        async def delayed_send(*args):
            sent.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()

        self.send.side_effect = delayed_send
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("forgotten health text", []))):
            await self.bot.receive(incoming("test"), None)
            await asyncio.wait_for(sent.wait(), timeout=1)
            tasks = list(self.bot.tasks.values())
            self.bot.forget(1)
            self.bot.set_session(1, legacy(3))
            release.set()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(self.bot.session(1)["history"], [])
        self.assertNotIn("forgotten health text", str(self.data))

    async def test_urgent_backstop_preserves_opted_in_record_but_not_unsaved_text(self):
        previous = self.bot.start_consultation(1, retain_history=True)
        self.bot.close_consultation(1, previous["id"])
        current = self.bot.start_consultation(1, retain_history=True)
        with patch("salchicher.generate_care_reply", AsyncMock()) as provider:
            await self.bot.receive(incoming("No puedo respirar"), None)
        provider.assert_not_awaited()
        self.send.assert_awaited_once_with(1, EMERGENCY_TEXT)
        result = self.bot.get_consultation(1, current["id"])
        self.assertEqual(result["status"], "inactive")
        self.assertEqual(result["closure_reason"], "urgent_help")
        self.assertEqual(len(result["messages"]), 3)
        self.assertIsNotNone(self.bot.get_consultation(1, previous["id"]))
        self.assertIsNone(self.bot.active_consultation(1))
        self.notify.assert_not_awaited()
        unsaved = self.bot.start_consultation(1, retain_history=False)
        await self.bot.receive(incoming("No puedo respirar"), None)
        self.assertIsNone(self.bot.get_consultation(1, unsaved["id"]))

    async def test_summary_uses_only_actual_vetted_assistant_care(self):
        episode = self.bot.start_consultation(1, retain_history=True)
        with patch("salchicher.generate_care_reply", AsyncMock(return_value=("Te escucho.", []))):
            await self.bot.receive(incoming(CARE["rest"] + " Mi diagnóstico inventado"), None)
            await self.finish()
        self.assertEqual(self.bot.get_consultation(1, episode["id"])["care_summary"], [])
        # Returned records cannot be mutated to alter persistence.
        detached = self.bot.get_consultation(1, episode["id"])
        detached["messages"].clear()
        self.assertGreater(len(self.bot.get_consultation(1, episode["id"])["messages"]), 0)


if __name__ == "__main__":
    unittest.main()
