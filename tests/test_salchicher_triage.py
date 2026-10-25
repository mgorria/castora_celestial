"""Synthetic text examples for the deliberately limited urgent backstop."""

import unittest

from salchicher_triage import urgent_signal


class UrgentSignalTests(unittest.TestCase):
    def test_isolated_headache_intensity_or_duration_never_triggers_112(self):
        for text in (
            "Me duele la cabeza", "Me duele mucho la cabecita", "Me duele muy fuerte la cabeza",
            "Tengo un dolor de cabeza fuerte", "Tengo un dolor de cabeza muy intenso",
            "Me duele la cabeza desde hace días", "Me duele la cabeza desde hace una semana y mucho",
            "Tengo migraña", "Tengo migraña muy fuerte desde ayer",
            "Me explota la cabeza de tanto trabajo", "Estoy agotada y necesito mojo de Oso",
        ):
            with self.subTest(text=text):
                self.assertFalse(urgent_signal(text))

    def test_explicit_sudden_explosive_or_worst_headache_is_recognized(self):
        for text in (
            "Tengo un dolor de cabeza repentino y explosivo",
            "De repente tengo un dolor explosivo de cabeza",
            "De repente tengo dolor de cabeza muy fuerte",
            "Me ha empezado de repente un dolor de cabeza como un trueno, es el peor de mi vida",
            "Tengo el peor dolor de cabeza de mi vida",
            "Ahora me duele la cabeza de golpe y de forma insoportable",
            "Tengo una cefalea súbita, violentísima",
            "Tengo un dolor de cabeza de repente, ha llegado a máxima intensidad en segundos",
        ):
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))

    def test_direct_current_danger_statements_remain_recognized(self):
        for text in (
            "No puedo respirar", "Me cuesta respirar", "Me falta mucho el aire",
            "Me estoy ahogando", "Me duele el pecho", "Tengo dolor fuerte en el pecho",
            "Tengo los labios morados", "Se me ha puesto la lengua hinchada",
            "Me he desmayado", "No puedo tragar", "No puedo beber agua",
            "Tengo un sangrado incontrolable", "Estoy sangrando sin parar",
        ):
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))

    def test_explicit_current_neurological_loss_is_recognized(self):
        for text in (
            "Ahora no puedo articular las palabras", "Hablo arrastrando las palabras",
            "De repente no puedo hablar",
            "Se me ha torcido la cara", "Ahora no puedo mover el brazo derecho",
            "De repente no puedo levantar la pierna izquierda",
            "No puedo mover un lado de mi cuerpo", "Acabo de perder la visión",
            "Ahora no veo nada por un ojo",
        ):
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))

    def test_negations_idioms_and_historical_stories_are_not_current_alerts(self):
        for text in (
            "No me cuesta respirar y no tengo dolor en el pecho",
            "No me he desmayado", "No tengo los labios morados", "No tengo la lengua hinchada",
            "No tengo sangrado abundante", "No tengo un dolor de cabeza explosivo",
            "Tengo dolor de cabeza, no es el peor de mi vida", "No tengo un dolor de cabeza repentino y explosivo",
            "Tengo dolor de cabeza muy fuerte, no empezó de repente",
            "Tengo dolor de cabeza repentino, no fue explosivo",
            "No puedo respirar de la risa con ese pato", "Me estoy ahogando en papeleo",
            "Ayer tuve dolor en el pecho, mi médico me atendió y ya estoy bien",
            "Ayer tuve dolor en el pecho, ahora solo me duele la cabeza",
            "El año pasado tuve un dolor de cabeza repentino y explosivo",
            "Ayer no podía respirar, ya se me pasó", "No puedo beber vino",
            "¿Qué significa la frase no puedo respirar?", "En la película tengo los labios morados",
        ):
            with self.subTest(text=text):
                self.assertFalse(urgent_signal(text))

    def test_denials_or_past_story_do_not_cancel_a_separate_real_signal(self):
        for text in (
            "No tengo dolor en el pecho pero no puedo respirar",
            "No tengo dolor en el pecho y no puedo respirar",
            "No puedo respirar de la risa; pero ahora me duele el pecho",
            "Ayer tuve dolor en el pecho y ya estoy bien, pero ahora no puedo respirar",
            "No me cuesta respirar, tengo un sangrado incontrolable",
            "No tengo dolor de cabeza pero ahora no puedo mover el brazo derecho",
            "No tengo fiebre, tengo el peor dolor de cabeza de mi vida",
        ):
            with self.subTest(text=text):
                self.assertTrue(urgent_signal(text))

    def test_current_since_yesterday_is_not_treated_as_a_past_story(self):
        self.assertTrue(urgent_signal("Desde ayer me duele el pecho"))
        self.assertTrue(urgent_signal("Hoy tengo dolor en el pecho"))
        self.assertFalse(urgent_signal("Desde ayer me duele la cabeza"))

    def test_empty_or_non_text_is_not_a_report(self):
        for text in (None, 0, [], "", "   "):
            self.assertFalse(urgent_signal(text))


if __name__ == "__main__":
    unittest.main()
