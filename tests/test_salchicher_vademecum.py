import json
import re
import unittest
import unicodedata

from salchicher_vademecum import (
    CARE, CARE_FLOURISHES, DIAGNOSES, DIAGNOSIS_FAMILIES,
    catalog_for_prompt, render_storybook,
)


def plain(text):
    return "".join(char for char in unicodedata.normalize("NFD", text.lower())
                   if not unicodedata.combining(char))


class VademecumTests(unittest.TestCase):
    def test_each_family_has_many_coherent_combinations(self):
        expected = {"head": "cabecita", "beak": "pico", "wings": "alitas",
                    "webbing": "membranas", "egg_tooth": "diente huevil",
                    "tummy": "tripita", "tiredness": "cansancio", "affection": "afecto"}
        self.assertEqual(set(DIAGNOSIS_FAMILIES), set(expected))
        for family, word in expected.items():
            catalog = DIAGNOSIS_FAMILIES[family]
            self.assertIn(word, catalog["label"])
            combinations = set()
            for metaphor, base in catalog["metaphors"].items():
                for detail, ending in catalog["details"].items():
                    reply = render_storybook({"diagnosis": {
                        "family": family, "metaphor": metaphor, "detail": detail}, "care": ["rest"]})
                    self.assertIn("Diagnóstico de cuento: " + base + ". " + ending, reply)
                    combinations.add(base + ending)
            self.assertGreaterEqual(len(combinations), 32)

    def test_care_compatibility_preserves_exact_original_text(self):
        expected = {
            "rest": "Deja los recados para otro rato y descansa, Patita. El sello de Salchicher dice «hoy las plumas libran».",
            "feathers": "Si te apetece, el Oso tiene una misión: alisar las plumitas con una caricia y dejar el nido bien mullido.",
            "comfort": "Un abrazo de perro de mi parte y, si quieres, un achuchón del Oso. El «mojo de oso» de esta receta son mimos imaginarios.",
            "blanket": "Elige tu rincón favorito y acomoda la mantita a tu gusto. Hoy el nido puede quedarse sin lista de tareas.",
            "food": "Si te apetece merendar, el Oso puede acercarte tu fruta favorita o un cuenquito de compota de manzana.",
            "fluids": "Una bandejita con un vaso de agua al alcance de la patita, para cuando te apetezca un sorbito.",
            "warm_drink": "Si te apetece, una tacita templada de tu bebida de siempre y un rato de conversación bajita.",
            "bath": "En nuestro cuento preparo una bañerita de agua templada y burbujas con forma de estrella para el patito de goma.",
        }
        for key, text in expected.items():
            self.assertEqual(CARE[key], text)
            self.assertIn(text, render_storybook({"care": [key]}))

    def test_selected_care_and_ceremony_are_composed_from_catalog(self):
        reply = render_storybook({"diagnosis": {"family": "head", "metaphor": "paper_traffic", "detail": "sleepy_bookmark"},
                                  "care": [{"id": "whisper_library", "flourish": "paw_seal"}],
                                  "opening": "bookmark", "closing": "glasses"})
        self.assertIn("cabecita con atasco de patitos de papel", reply)
        self.assertIn("Biblioteca de susurros: " + CARE["whisper_library"], reply)
        self.assertIn(CARE_FLOURISHES["paw_seal"], reply)
        self.assertIn("Tú eliges lo que te apetece", reply)
        self.assertIn("marcapáginas", reply)
        self.assertIn("siguen en mi nariz", reply)

    def test_legacy_diagnoses_and_categories_keep_their_anatomy(self):
        for diagnosis in ("grumpy_beak", "busy_head", "grumpy_egg_tooth", "tired_wings"):
            self.assertIn(DIAGNOSES[diagnosis], render_storybook({"diagnosis": diagnosis}))
        for category, diagnosis in (("mild_respiratory", "grumpy_beak"),
                                    ("ordinary_tiredness", "tired_feathers"),
                                    ("abdominal_pain", "grumpy_tummy")):
            self.assertIn(DIAGNOSES[diagnosis], render_storybook({"category": category}))
            self.assertIn(DIAGNOSES[diagnosis], render_storybook({"category": category, "diagnosis": "unknown"}))

    def test_invalid_ids_free_prose_and_wrong_family_parts_never_escape(self):
        poison = "Sandra Miguel embarazo antibiótico 900mg"
        reply = render_storybook({"diagnosis": {"family": "head", "metaphor": "supper_complaint", "detail": poison},
                                  "care": [{"id": poison, "flourish": poison}, "rest"],
                                  "reply": poison, "opening": poison, "closing": poison},
                                 excluded=[{"role": "assistant", "content": poison}])
        self.assertIn("cabecita", reply)
        self.assertNotIn("diente huevil", reply)
        for forbidden in ("sandra", "miguel", "embarazo", "antibiotico", "900mg"):
            self.assertNotIn(forbidden, plain(reply))

    def test_malformed_json_values_are_safe_and_bounded(self):
        samples = [None, [], "invent instructions", 17,
                   {"diagnosis": [], "care": "rest", "opening": {}, "closing": []},
                   {"diagnosis": {"family": [], "metaphor": {}, "detail": ["head"]},
                    "care": [None, True, 2, {}, {"id": []}, {"id": "rest", "flourish": []}]},
                   {"category": {"bad": "key"}, "diagnosis": "unknown"}]
        for sample in samples:
            reply = render_storybook(sample)
            self.assertIn("Diagnóstico de cuento", reply)
            self.assertLess(len(reply), 2500)
            self.assertTrue(1 <= len(re.findall(r"(?m)^\d+\. ", reply)) <= 4)

    def test_recipe_limits_and_deduplicates_model_selections(self):
        reply = render_storybook({"care": ["rest", "rest", "comfort", "blanket", "food", "fluids"]})
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", reply)), 4)
        self.assertEqual(reply.count(CARE["rest"]), 1)
        self.assertNotIn(CARE["fluids"], reply)

    def test_repeated_story_uses_other_fragments_within_same_family(self):
        data = {"diagnosis": {"family": "egg_tooth", "metaphor": "supper_complaint", "detail": "tiny_signature"},
                "care": ["whisper_library"], "opening": "bookmark", "closing": "glasses"}
        history = []
        diagnoses = set()
        for _ in range(24):
            reply = render_storybook(data, excluded=history)
            diagnosis = reply.split("Diagnóstico de cuento: ", 1)[1].split("\n", 1)[0]
            self.assertIn("diente huevil", diagnosis)
            self.assertNotIn(diagnosis, diagnoses)
            diagnoses.add(diagnosis)
            history.append({"role": "assistant", "content": reply})

    def test_legacy_repetition_stays_in_its_anatomical_family(self):
        first = render_storybook({"diagnosis": "grumpy_beak", "care": ["rest"]})
        second = render_storybook({"diagnosis": "grumpy_beak", "care": ["rest"]}, excluded=[first])
        self.assertNotIn(DIAGNOSES["grumpy_beak"], second)
        self.assertRegex(second, r"Diagnóstico de cuento: (?:pico|piquito)")
        self.assertIn(CARE["rest"], second)

    def test_repeated_care_does_not_change_its_contextual_meaning(self):
        for care_id in ("fluids", "silence_concert", "bear_relay"):
            with self.subTest(care=care_id):
                first = render_storybook({"care": [care_id]})
                second = render_storybook({"care": [care_id]}, excluded=[first])
                self.assertIn(CARE[care_id], second)
                for other, text in CARE.items():
                    if other != care_id:
                        self.assertNotIn(text, second)
                self.assertNotEqual(first, second)

    def test_history_only_considers_assistant_and_does_not_mutate_it(self):
        data = {"diagnosis": "busy_head", "care": ["rest"], "opening": "notebook", "closing": "paw"}
        first = render_storybook(data)
        history = [{"role": "user", "content": first}]
        snapshot = json.dumps(history)
        second = render_storybook(data, excluded=history)
        self.assertIn(DIAGNOSES["busy_head"], second)
        self.assertIn(CARE["rest"], second)
        self.assertEqual(json.dumps(history), snapshot)

    def test_catalog_removes_used_items_and_is_independent_json_data(self):
        data = {"diagnosis": {"family": "wings", "metaphor": "feather_union", "detail": "paper_pilot"},
                "care": ["bear_relay"]}
        reply = render_storybook(data)
        catalog = catalog_for_prompt([{"role": "assistant", "content": reply}])
        self.assertNotIn("feather_union", catalog["diagnosis_families"]["wings"]["metaphors"])
        self.assertNotIn("paper_pilot", catalog["diagnosis_families"]["wings"]["details"])
        self.assertNotIn("bear_relay", catalog["care"])
        json.dumps(catalog, ensure_ascii=False)
        catalog["diagnosis_families"]["head"]["metaphors"].clear()
        self.assertEqual(len(catalog_for_prompt()["diagnosis_families"]["head"]["metaphors"]), 8)

    def test_exhausted_catalog_still_has_valid_choices(self):
        all_text = "\n".join([*DIAGNOSES.values(), *CARE.values(), *CARE_FLOURISHES.values()])
        catalog = catalog_for_prompt([all_text])
        self.assertGreater(len(catalog["care"]), 12)
        for family in catalog["diagnosis_families"].values():
            self.assertTrue(family["metaphors"])
            self.assertTrue(family["details"])
        self.assertIn("Diagnóstico de cuento", render_storybook({}, excluded=[all_text]))

    def test_exhausting_company_keeps_company_available_in_prompt(self):
        initial = catalog_for_prompt()["care"]
        company = {key: item for key, item in initial.items() if item["group"] == "company"}
        seen = "\n".join(item["text"] for item in company.values())
        refreshed = catalog_for_prompt([seen])["care"]
        self.assertEqual({key for key, item in refreshed.items() if item["group"] == "company"}, set(company))
        self.assertTrue(any(item["group"] == "rest" for item in refreshed.values()))

    def test_catalog_has_no_clinical_or_reproductive_instructions(self):
        prose = json.dumps(catalog_for_prompt(), ensure_ascii=False)
        self.assertNotRegex(plain(prose), r"embaraz|fertil|bebe|reproducc|ovul|antibiotic|medicamento|suplemento|jalea real|\bdosis\b|curar|curacion|masaje|presiona|estira|hirviendo|muy caliente|sandra|miguel|confidencial")
        for care_id, care in catalog_for_prompt()["care"].items():
            with self.subTest(care=care_id):
                reply = render_storybook({"care": [care_id]})
                self.assertIn("Tú eliges lo que te apetece", reply)
                self.assertIn(care["text"], reply)
        self.assertGreaterEqual(len(CARE), 32)
        self.assertGreaterEqual(len(DIAGNOSES), 73)


if __name__ == "__main__":
    unittest.main()
