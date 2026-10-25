"""Bounded conversational copy and reversible filtering of retired templates.

These literals are frozen versions of the old templates, not matching rules for
personal topics. User messages and similar manually written text stay intact.
No source history or read metadata is changed by this module.
"""

from itertools import permutations


# Only these authored sentences can be selected for brief conversational turns.
# Their IDs may be remembered between visits without retaining patient details.
REPLIES = {
    "greeting": {
        "hello": "Hola, Patita. Te escucho.",
        "welcome": "Qué gusto verte por aquí, solete. Pasa cuando quieras.",
        "room": "Hay sitio para ti y para lo que quieras contarme. Adelante, Patita.",
    },
    "thanks": {
        "welcome": "De nada, Patita. Me alegra hacerte compañía.",
        "simple": "Para eso estamos, solete.",
        "gift": "Ese cariño no necesita devolución. Un cuac bajito de mi parte.",
    },
    "farewell": {
        "bye": "Hasta luego, Patita. Que tengas un ratito agradable.",
        "wave": "Nos vemos, solete. Te digo adiós con la patita desde aquí.",
        "later": "Hasta la próxima, Patita. Aquí estaré cuando quieras volver.",
    },
    "goodnight": {
        "night": "Buenas noches, Patita. Ojalá encuentres un descanso a tu gusto.",
        "quiet": "Hasta mañana, solete. Dejamos la charla aquí y bajamos la voz.",
        "bye": "Descansa a tu aire, Patita. Te mando un beso de buenas noches, si te apetece.",
    },
    "acknowledgment": {
        "heard": "Te escucho, Patita. Puedes seguir a tu ritmo.",
        "space": "No hace falta contarlo todo de golpe. Aquí tienes compañía.",
        "here": "Sigo aquí, solete.",
    },
    "identity": {
        "doctor": "En nuestra historia soy el Doctor Salchicher, el perro de este consultorio de cuento. Atiendo patos y preparo recetas de mimos.",
        "work": "En nuestra historia soy un perrito salchicha con bata. Mi especialidad son los cuidados de cuento para Patita.",
        "name": "Doctor Salchicher, para servirte. Un perro entre patos, con mucho cariño y un cuaderno de mimos.",
    },
    "comfort": {
        "quiet": "Estoy aquí, Patita. Podemos quedarnos un ratito sin tener que arreglar nada.",
        "hug": "Si te apetece, va un abrazo de perro de mi parte. También puedo acompañarte sin decir mucho.",
        "pause": "Por un momento dejamos los recados fuera de esta charla. No tienes que hacer méritos para recibir cariño.",
        "note": "Te dejo una nota firmada con mi patita: «Hoy también hay sitio para ti». No necesita respuesta.",
    },
    "consultation": {
        "listen": "Cuéntame qué te trae hoy por aquí, Patita. Te escucho.",
        "begin": "Ya puedes pasar, solete. Empezamos por lo que tú quieras contarme.",
        "visit": "Hola, Patita. ¿Qué te gustaría contarme en esta visita?",
    },
    "invitation": {
        "door": "Soy el Doctor Salchicher. En este consultorio de cuento atiendo a los patos con cariño. Si te apetece, pasa y charlamos.",
        "welcome": "Bienvenida al consultorio de cuento, Patita. Hay sitio para una charla y para una receta de mimos, si la quieres.",
        "choice": "Hola, solete. Puedes pasar a contarme lo que quieras; también vale venir solo por un poquito de compañía.",
    },
    "resume": {
        "continue": "Seguimos donde lo dejamos, Patita. Te escucho.",
        "ready": "Estoy por aquí, solete. No hace falta empezar de nuevo.",
        "room": "Cuando quieras seguimos con nuestra charla. A tu ritmo.",
    },
    "unavailable": {
        "pause": "Me he quedado a medias con la respuesta, Patita. Puedes volver a escribirme dentro de un ratito.",
        "here": "Hoy las palabras se me están atascando un poco. Sigo aquí, solete; lo intentamos de nuevo en un momento.",
    },
}


def assistant_texts(history):
    """Only actual assistant turns count as prior use, never a user's quotation."""
    if not isinstance(history, (list, tuple)):
        return []
    return [entry["content"] for entry in history if isinstance(entry, dict)
            and entry.get("role") == "assistant" and isinstance(entry.get("content"), str)][-24:]


def select_reply(kind, history=None):
    choices = REPLIES[kind]
    previous = assistant_texts(history)
    # Prefer an unused sentence of the right conversational intent. When all
    # have appeared, reuse the least recent, rather than repeating the last one.
    def last_used(item):
        _, text = item
        return max((index for index, turn in enumerate(previous) if text in turn), default=-1)
    return min(choices.items(), key=last_used)[1]


def reply_style_ids(text):
    if not isinstance(text, str):
        return []
    return [f"{kind}:{key}" for kind, choices in REPLIES.items() for key, sentence in choices.items()
            if sentence in text]


def reply_style_history(ids):
    """Expand known style IDs only; arbitrary stored text is never interpolated."""
    lookup = {f"{kind}:{key}": sentence for kind, choices in REPLIES.items() for key, sentence in choices.items()}
    return [{"role": "assistant", "content": lookup[key]} for key in ids[-24:]
            if isinstance(key, str) and key in lookup] if isinstance(ids, list) else []


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
