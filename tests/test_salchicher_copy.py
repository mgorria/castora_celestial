"""Synthetic regression fixtures for retired automatic consultation text."""

import unittest
from itertools import permutations

from salchicher_copy import (
    LEGACY_GREETING, LEGACY_INTRO, LEGACY_QUESTIONS, retired_automatic_message,
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


if __name__ == "__main__":
    unittest.main()
