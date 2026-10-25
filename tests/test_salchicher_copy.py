"""Synthetic regression fixtures for retired automatic consultation text."""

import unittest
from itertools import permutations

from salchicher_copy import (
    LEGACY_GREETING, LEGACY_INTRO, LEGACY_QUESTIONS, retired_automatic_message,
    REPLIES, select_reply, reply_style_ids, reply_style_history,
)


class RetiredCopyTests(unittest.TestCase):
    def test_exact_former_greetings_are_hidden_only_for_assistant(self):
        for text in (LEGACY_GREETING, LEGACY_INTRO):
            for field in ("content", "text"):
                with self.subTest(field=field, text=text[:20]):
                    self.assertTrue(retired_automatic_message({"role": "assistant", field: text}))
                    self.assertFalse(retired_automatic_message({"role": "user", field: text}))

    def test_old_renderer_combinations_only_hide_context_question(self):
        for size in (1, 2):
            for keys in permutations(LEGACY_QUESTIONS, size):
                for prefix in ("Me ajusto las gafitas y te escucho, patita. ",
                               "Gracias por contármelo, solete. "):
                    text = prefix + "\n\n".join(LEGACY_QUESTIONS[key] for key in keys)
                    with self.subTest(keys=keys, prefix=prefix):
                        self.assertEqual(retired_automatic_message({"role": "assistant", "text": text}),
                                         "context" in keys)
                        self.assertFalse(retired_automatic_message({"role": "user", "text": text}))

    def test_similar_manual_text_and_unrecognized_shapes_are_preserved(self):
        context = LEGACY_QUESTIONS["context"]
        for text in (context, "Comentario manual: " + context,
                     "Gracias por contármelo, solete. " + context + " Te escucho.",
                     LEGACY_GREETING + " ", "Sandra y Miguel han escrito una nota.",
                     "No quiero preguntas sobre embarazo."):
            self.assertFalse(retired_automatic_message({"role": "assistant", "text": text}))
        for message in (None, {}, {"role": "assistant", "text": None}):
            self.assertFalse(retired_automatic_message(message))


class ConversationalCopyTests(unittest.TestCase):
    def test_variation_uses_assistant_history_not_user_quotations(self):
        first = select_reply("comfort")
        self.assertEqual(select_reply("comfort", [{"role": "user", "content": first}]), first)
        second = select_reply("comfort", [{"role": "assistant", "content": first}])
        self.assertNotEqual(second, first)
        history = [{"role": "assistant", "content": text} for text in REPLIES["comfort"].values()]
        self.assertNotEqual(select_reply("comfort", history), history[-1]["content"])
        self.assertNotIn("gafitas", first + second)

    def test_style_memory_contains_only_fixed_copy_ids(self):
        sentence = select_reply("greeting")
        ids = reply_style_ids(sentence + " Me duele la cabeza desde ayer. TEXTO_PERSONAL")
        self.assertEqual(ids, ["greeting:hello"])
        self.assertEqual(reply_style_history([*ids, "TEXTO_PERSONAL", "unknown:head", {}]),
                         [{"role": "assistant", "content": sentence}])


if __name__ == "__main__":
    unittest.main()
