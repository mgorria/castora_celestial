"""Reversible display filtering for a closed set of retired automatic copy.

These literals are frozen versions of the old templates, not matching rules for
personal topics. User messages and similar manually written text stay intact.
No source history or read metadata is changed by this module.
"""

from itertools import permutations


LEGACY_GREETING = (
    "¡Adelante, patita! Te guardé el sillón junto a la ventana. Me pongo las gafitas "
    "y abro nuestro cuaderno de cuidados, que podéis leer tú y el Oso. Cuéntame qué notas y desde cuándo, "
    "y vamos pasito a pasito."
)
LEGACY_INTRO = (
    "¡Adelante, patita! Soy el Doctor Salchicher. Me acomodo las gafitas y te guardo "
    "el sillón de los cuidados y los mimos. Aquí buscamos un poquito de comodidad; "
    "para saber qué te pasa o decidir un tratamiento hace falta un profesional sanitario.\n\n"
    "Este cuaderno se conserva hasta 48 horas desde tu último mensaje y no pasa a "
    "los cuentos. Puedes borrarlo con /olvidar; eso no borra las copias que ya existan "
    "fuera de mi cuaderno ni otros registros del servicio. Tú eliges si el Oso recibe copia.\n\n"
    "Si es una urgencia, busca ayuda sin esperar y llama al 112."
)
LEGACY_QUESTIONS = {
    "symptoms": "Cuéntame qué notas y qué es lo que más te molesta, patita; te escucho con las dos orejas.",
    "duration": "¿Desde cuándo te pasa, solete? ¿Va a mejor, sigue igual o está empeorando?",
    "severity": "¿Cómo de fuerte lo notas: leve, o te impide hacer lo habitual? ¿Te has medido la fiebre?",
    "breathing": "Una comprobación importante, patita: ¿respiras con normalidad y puedes beber y tragar sin dificultad?",
    "context": "Para cuidarte con prudencia: ¿hay embarazo, alguna enfermedad importante o indicación médica que deba tener en cuenta?",
    "honey": "Antes de pensar en miel, solete: ¿tienes alergia a ella o a productos de las abejas, o te han indicado evitarlos?",
}
_PREFIXES = ("Me ajusto las gafitas y te escucho, patita. ", "Gracias por contármelo, solete. ")
_RETIRED_TEXTS = frozenset({LEGACY_GREETING, LEGACY_INTRO} | {
    prefix + "\n\n".join(LEGACY_QUESTIONS[key] for key in keys)
    for size in (1, 2)
    for keys in permutations(LEGACY_QUESTIONS, size)
    if "context" in keys
    for prefix in _PREFIXES
})


def retired_automatic_message(message: dict) -> bool:
    """Match only complete former automatic assistant messages, byte for byte."""
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return False
    text = message.get("text", message.get("content"))
    return isinstance(text, str) and text in _RETIRED_TEXTS
