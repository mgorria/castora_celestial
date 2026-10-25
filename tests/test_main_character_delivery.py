"""Private editorial guardrails never send rejected text to the recipient."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

import main


class CharacterDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_doctor_delivery_is_visible_in_shared_consultation(self):
        owner_chat = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=owner_chat, message=object())
        context = SimpleNamespace(args=['Te', 'acerco', 'una', 'mantita.'])
        animal_bot = SimpleNamespace(send_message=AsyncMock(), send_chat_action=AsyncMock())
        doctor = SimpleNamespace(active_consultation=Mock(return_value={'id': 'care-one'}), record_manual_delivery=Mock())
        with patch.object(main, 'is_owner', return_value=True), \
             patch.object(main, 'get_partner_chat_id', return_value=11), \
             patch.object(main, 'animal_apps', {'salchicher': SimpleNamespace(bot=animal_bot)}), \
             patch.object(main, 'salchicher', doctor), patch.object(main, 'append_history'):
            await main.send_as_animal('salchicher', update, context)
        animal_bot.send_message.assert_awaited_once_with(chat_id=11, text='Te acerco una mantita.')
        doctor.record_manual_delivery.assert_called_once_with(11, 'Te acerco una mantita.', 'care-one')

    async def test_scheduled_doctor_archive_failure_never_retries_successful_delivery(self):
        animal_bot = SimpleNamespace(send_message=AsyncMock(), send_chat_action=AsyncMock())
        doctor = SimpleNamespace(active_consultation=Mock(return_value={'id': 'care-one'}),
                                 record_manual_delivery=Mock(side_effect=RuntimeError('storage')))
        with patch.object(main, 'get_partner_chat_id', return_value=11), \
             patch.object(main, 'animal_apps', {'salchicher': SimpleNamespace(bot=animal_bot)}), \
             patch.object(main, 'salchicher', doctor), patch.object(main, 'append_history'), \
             patch.object(main, 'centralita_app', None):
            result = await main.send_scheduled_message({'id':'care-schedule', 'animal_key':'salchicher', 'text':'Un abrazo, patita.'})
        self.assertTrue(result)
        animal_bot.send_message.assert_awaited_once()

    async def test_owner_accusation_cannot_echo_a_technical_aside_to_sandra(self):
        owner_chat = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=owner_chat)
        context = SimpleNamespace(args=['Este', 'mensaje', 'lo', 'envía', 'un', 'bot.'])
        with patch.object(main, 'is_owner', return_value=True), \
             patch.object(main.database, 'db_available', return_value=True), \
             patch.object(main, 'openai_available', return_value=True), \
             patch.object(main.database, 'create_court_case', AsyncMock()) as create, \
             patch.object(main, 'get_partner_chat_id') as recipient:
            await main.central_accuse(update, context)
        create.assert_not_awaited()
        recipient.assert_not_called()
        self.assertIn('no se ha abierto ninguna causa', owner_chat.send_message.call_args.args[0])

    async def test_manual_message_is_rejected_privately_without_rewriting_it(self):
        owner_chat = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=owner_chat, message=object())
        context = SimpleNamespace(args=['Soy', 'un', 'bot', 'de', 'Telegram.'])
        with patch.object(main, 'is_owner', return_value=True), patch.object(main, 'get_partner_chat_id') as recipient:
            await main.send_as_animal('castori', update, context)
        recipient.assert_not_called()
        owner_chat.send_message.assert_awaited_once()
        self.assertIn('No se ha enviado', owner_chat.send_message.call_args.args[0])
        self.assertEqual(context.args, ['Soy', 'un', 'bot', 'de', 'Telegram.'])

    async def test_new_schedule_rejects_technical_aside_before_persisting(self):
        owner_chat = SimpleNamespace(send_message=AsyncMock())
        update = SimpleNamespace(effective_chat=owner_chat)
        context = SimpleNamespace(args=['mimosuga', 'lunes', '09:00', 'Como', 'IA,', 'te', 'respondo.'])
        with patch.object(main, 'is_owner', return_value=True), patch.object(main, 'save_schedules') as save:
            await main.central_schedule(update, context)
        save.assert_not_called()
        self.assertIn('No se ha guardado', owner_chat.send_message.call_args.args[0])

    async def test_old_review_stays_pending_and_never_reaches_animal(self):
        draft = {'animal_key':'mimosuga', 'proposed_text':'Como modelo de lenguaje no tengo cuerpo.'}
        with patch.object(main.database, 'reserve_auto_reply_draft', AsyncMock(return_value=draft)), \
             patch.object(main.database, 'release_auto_reply_draft', AsyncMock()) as release, \
             patch.object(main, 'get_partner_chat_id') as recipient:
            sent, message = await main.send_auto_reply_draft(12, 22)
        self.assertFalse(sent)
        self.assertIn('se conserva pendiente', message)
        release.assert_awaited_once_with(12)
        recipient.assert_not_called()
        self.assertEqual(draft['proposed_text'], 'Como modelo de lenguaje no tengo cuerpo.')

    async def test_legacy_schedule_is_stopped_once_and_original_preserved(self):
        schedules = [{'id':'legacy', 'kind':'weekly', 'animal_key':'mimosuga', 'weekday':0,
                      'time':'09:00', 'text':'Este mensaje lo genera OpenAI.'}]
        animal_bot = SimpleNamespace(send_message=AsyncMock(), send_chat_action=AsyncMock())
        owner_bot = SimpleNamespace(send_message=AsyncMock())
        def save(rows):
            schedules[:] = copy.deepcopy(rows)
        with patch.object(main, 'get_schedules', side_effect=lambda:copy.deepcopy(schedules)), \
             patch.object(main, 'save_schedules', side_effect=save), \
             patch.object(main, 'get_partner_chat_id', return_value=11), \
             patch.object(main, 'owner_chat_id', return_value=22), \
             patch.object(main, 'animal_apps', {'mimosuga':SimpleNamespace(bot=animal_bot)}), \
             patch.object(main, 'centralita_app', SimpleNamespace(bot=owner_bot)):
            self.assertFalse(await main.send_scheduled_message(copy.deepcopy(schedules[0])))
            self.assertIsNone(main.mark_schedule_before_send('legacy', '2026-10-26'))
            self.assertFalse(await main.send_scheduled_message(copy.deepcopy(schedules[0])))
        self.assertEqual(schedules[0]['text'], 'Este mensaje lo genera OpenAI.')
        self.assertEqual(schedules[0]['blocked_reason'], 'character_voice')
        animal_bot.send_message.assert_not_awaited()
        owner_bot.send_message.assert_awaited_once()
        self.assertEqual(owner_bot.send_message.call_args.kwargs['chat_id'], 22)
        self.assertIn('Detenido', main.format_schedule(schedules[0]))


if __name__ == '__main__':
    unittest.main()
