"""Small text backstop for explicit urgent statements, not a medical assessment.

False means only that none of this limited set of statements was recognized.
Headache intensity or duration alone never triggers this backstop. Sources for
the few added headache/neurological statements (checked 2026-10-25):
https://www.nhs.uk/symptoms/headaches/
https://www.nhs.uk/conditions/stroke/symptoms/
https://medlineplus.gov/ency/patientinstructions/000424.htm
"""

import re
import unicodedata


def _normalized(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFD", text.lower())
                   if not unicodedata.combining(char))


_FIGURES = re.compile(
    r"\bno (?:puedo|consigo) respirar de (?:la )?risa\b|"
    r"\bme (?:estoy )?ahogando (?:de risa|en (?:el )?(?:papeleo|trabajo))\b|"
    r"\b(?:me explota|me va a explotar) la cabeza (?:de|con) (?:tanto |el )?(?:trabajo|papeleo)\b"
)
_CLAUSES = re.compile(
    r"[.;!?\n]+|\b(?:pero|sin embargo)\b|"
    r"\by\s+(?=(?:ahora|hoy|no|me|tengo|estoy|siento|noto|se me|he perdido|ya)\b)"
)
_CURRENT = re.compile(r"\b(?:ahora|hoy|en este momento|todavia|sigo|sigue|desde)\b")
_PAST = re.compile(
    r"\b(?:ayer|anteayer|anoche|la semana pasada|el ano pasado|hace anos|cuando era|"
    r"de pequena|tuve|tenia|sentia|notaba|me dolia|no podia|me costaba|me faltaba|"
    r"me ahogue|me desmaye)\b"
)
_RESOLVED = re.compile(r"\b(?:ya estoy bien|ya se (?:me )?paso|ya no me pasa|ya resuelto)\b")
_HYPOTHETICAL = re.compile(
    r"\b(?:que significa|que significa decir|por ejemplo|un ejemplo|la frase|"
    r"si algun dia|si me pasara|si tuviera|si no pudiera|en el cuento|en la pelicula)\b"
)
_NEGATIVE_PREFIX = re.compile(
    r"\b(?:no|nunca|ni|sin|niego)\s+"
    r"(?:(?:tengo|siento|noto|hay|presento|esta|estan|tiene|tienen|he|tenido|me|"
    r"ha|es|era|fue|cierto|verdad|que|empezo|aparecio|empezado|aparecido|"
    r"lo|los|la|el|las|un|una|mucho|nada|ningun|ninguna|ahora)\s+)*$"
)
_DIRECT = re.compile(
    r"\bno (?:puedo|consigo) respirar\b|"
    r"\bme (?:cuesta|falta) (?:mucho )?(?:respirar|el aire)\b|"
    r"\bme (?:estoy )?ahogando\b|"
    r"\b(?:(?:tengo|siento|noto) (?:un )?)?dolor (?:muy |fuerte |intenso )*(?:en (?:el )?|de )?pecho\b|"
    r"\bme duele (?:mucho )?el pecho\b|"
    r"\blabios (?:azules|morados)\b|"
    r"\b(?:lengua|garganta) (?:muy )?hinchada\b|"
    r"\bme he desmayado\b|"
    r"\bno puedo (?:tragar|beber)\b(?!\s+(?:alcohol|vino|cerveza|cafe)\b)|"
    r"\bsangrado (?:muy )?(?:abundante|incontrolable)\b|"
    r"\b(?:estoy sangrando|sangro) sin parar\b"
)
_NEUROLOGICAL = re.compile(
    r"\b(?:ahora|de repente|de pronto) no (?:puedo|consigo) hablar\b|"
    r"\bno (?:puedo|consigo) articular (?:las )?palabras\b|"
    r"\bhablo arrastrando (?:las )?palabras\b|"
    r"\bse me ha (?:torcido|caido) (?:un lado de )?la cara\b|"
    r"\bno (?:puedo|consigo) mover (?:un|el) lado (?:de mi|del) cuerpo\b|"
    r"\b(?:ahora|de repente|de pronto) no (?:puedo|consigo) (?:mover|levantar) "
    r"(?:el|un|la|una) (?:brazo|pierna)(?: (?:derech[oa]|izquierd[oa]))?\b|"
    r"\b(?:he perdido|acabo de perder) (?:de repente )?la (?:vision|vista)\b|"
    r"\bno veo nada (?:por|con) (?:un|el) ojo\b"
)
_HEADACHE = re.compile(
    r"\b(?:dolor(?: (?:muy|fuerte|intenso|explosivo|repentino|subito|insoportable|violento|brutal))* "
    r"de (?:cabeza|cabecita)|cefalea|me duele (?:mucho |muy fuerte )?la (?:cabeza|cabecita))\b"
)
_SUDDEN = re.compile(r"\b(?:repentin[oa]|subit[oa]|de repente|de golpe|de pronto|como un trueno|en trueno)\b")
_EXTREME = re.compile(
    r"\b(?:explosiv[oa]|violent[oa]|violentisim[oa]|fortisim[oa]|intensisim[oa]|"
    r"insoportable|muy fuerte|muy intens[oa]|maxima intensidad en (?:pocos )?segundos)\b"
)
_WORST = re.compile(r"\b(?:el )?peor (?:dolor de (?:cabeza|cabecita) )?(?:de|en) (?:toda )?mi vida\b")


def _asserted(clause: str, pattern: re.Pattern) -> bool:
    for match in pattern.finditer(clause):
        # Negation applies locally, not to a different symptom after a comma.
        prefix = clause[:match.start()].rsplit(",", 1)[-1]
        if _PAST.search(prefix) and not _CURRENT.search(prefix):
            continue
        if not _NEGATIVE_PREFIX.search(prefix):
            return True
    return False


def urgent_signal(text: str) -> bool:
    """Recognize a few explicit current danger statements, without diagnosing."""
    if not isinstance(text, str) or not text.strip():
        return False
    value = _FIGURES.sub(" ", _normalized(text))
    for raw_clause in _CLAUSES.split(value):
        clause = raw_clause.strip(" ,:¿¡")
        if not clause or _HYPOTHETICAL.search(clause):
            continue
        # A dated story or a resolved old episode is not a new current report.
        # A separate present-tense statement remains a separate clause.
        if (_PAST.search(clause) or _RESOLVED.search(clause)) and not _CURRENT.search(clause):
            continue
        if _asserted(clause, _DIRECT) or _asserted(clause, _NEUROLOGICAL):
            return True
        if _asserted(clause, _HEADACHE):
            if _asserted(clause, _WORST):
                return True
            if _asserted(clause, _SUDDEN) and _asserted(clause, _EXTREME):
                return True
    return False
