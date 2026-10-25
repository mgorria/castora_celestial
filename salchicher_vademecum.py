"""Salchicher's composable storybook: selected fragments, never generated advice.

The selector may choose IDs from ``catalog_for_prompt``. Only the trusted words
below can reach ``render_storybook``. Previous assistant replies are used solely
to vary the next page; no conversation text is interpolated into a prescription.
"""

from collections.abc import Mapping
from random import SystemRandom
from typing import Any


_random = SystemRandom()

DIAGNOSIS_FAMILIES = {
    "head": {
        "label": "cabecita",
        "metaphors": {
            "quack_parliament": "cabecita con un parlamento de cuacs hablando a la vez",
            "open_library": "cabecita con demasiados libros de pensamientos abiertos",
            "paper_traffic": "cabecita con atasco de patitos de papel",
            "bell_committee": "cabecita con un comité de campanillas indecisas",
            "busy_lighthouse": "cabecita con el faro de las ideas haciendo horas de más",
            "cloud_archive": "cabecita con el archivo de nubecitas desordenado",
            "wandering_comma": "cabecita con una coma de cuento buscando dónde sentarse",
            "murmur_attic": "cabecita con el desván de murmullos abierto",
        },
        "details": {
            "quiet_margin": "En el margen del cuaderno queda una página sin recados.",
            "paper_hat": "El presidente de los cuacs lleva un sombrerito de papel.",
            "sleepy_bookmark": "El marcapáginas del expediente se ha quedado en pijama.",
            "cloud_clerk": "La secretaria de las nubes pide que le hablen bajito.",
        },
    },
    "beak": {
        "label": "pico",
        "metaphors": {
            "sigh_mailbox": "piquito con el buzón de suspiros lleno",
            "sunday_herald": "pico de pregonero que solicita domingo",
            "quack_strike": "piquito con los cuacs reunidos en asamblea",
            "scarf_bureau": "pico refunfuñón con expediente en la oficina de bufanditas",
            "tiny_trumpet": "piquito con una trompeta de cuento que pide entreacto",
            "message_balcony": "pico con demasiados pregones en el balcón",
            "pouting_stamp": "piquito con el sello de protesta puesto del revés",
            "whisper_envelope": "pico con un sobre de susurros pendiente de abrir",
        },
        "details": {
            "paper_scarf": "En la ilustración, la bufandita es de papel de lunares.",
            "little_postman": "El cartero de los cuacs ha dejado la gorra en el perchero.",
            "quiet_bell": "La campanilla del pregonero tiene hoy horario de biblioteca.",
            "quack_receipt": "El último cuac ha firmado el recibo con una pluma azul.",
        },
    },
    "wings": {
        "label": "alitas",
        "metaphors": {
            "errand_agenda": "alitas con demasiados recados en la agenda",
            "feather_union": "alitas con un sindicato de plumas que reclama sobremesa",
            "paper_airport": "alitas con el aeropuerto de papel en cambio de turno",
            "cloud_luggage": "alitas con demasiadas nubecitas en el equipaje",
            "wind_resignation": "alitas con una carta de dimisión del viento imaginario",
            "late_curtain": "alitas con el telón de los recados todavía abierto",
            "feather_pension": "alitas con solicitud de jubilación de aleteos de cuento",
            "sunday_hangar": "alitas con ganas de domingo en el hangar de las plumas",
        },
        "details": {
            "closed_ticket": "La taquilla de los recados cuelga un cartelito de «luego».",
            "paper_pilot": "El piloto de papel se ha puesto zapatillas de estar por casa.",
            "cloud_suitcase": "La maleta de las nubes lleva una etiqueta de sobremesa.",
            "feather_minutes": "El acta de la reunión está firmada por una pluma soñolienta.",
        },
    },
    "webbing": {
        "label": "membranas de las patitas",
        "metaphors": {
            "pond_letters": "membranas con correspondencia pendiente del estanque",
            "creased_map": "patitas con el mapa de recados arrugado",
            "dock_committee": "membranas con un comité del embarcadero pidiendo sobremesa",
            "paper_puddles": "patitas con demasiados charquitos dibujados en la agenda",
            "sock_office": "membranas con una reclamación en la oficina de calcetines imaginarios",
            "duck_footnotes": "patitas con demasiadas notas al pie del cuento",
            "shore_calendar": "membranas con el calendario de la orilla lleno de lunes",
            "reed_postcard": "patitas con una postal de los juncos que dice «sin prisas»",
        },
        "details": {
            "paper_dock": "En el mapa, el embarcadero tiene un banco de papel mullido.",
            "idle_compass": "La brújula del cuento señala el rincón favorito.",
            "pond_seal": "El estanque ha enviado un sello con forma de patita.",
            "shore_note": "Al pie de la página pone «la orilla puede esperar».",
        },
    },
    "egg_tooth": {
        "label": "diente huevil de pato de cuento",
        "metaphors": {
            "supper_complaint": "diente huevil con una reclamación de sobremesa",
            "grumpy_doorman": "diente huevil con un portero refunfuñón en su caseta de cuento",
            "tiny_megaphone": "diente huevil con un megáfono diminuto de protesta",
            "crooked_sign": "diente huevil con el cartelito de «hoy no estoy de humor» torcido",
            "paper_crown": "diente huevil con la corona de papel arrugada",
            "complaint_book": "diente huevil con el libro de reclamaciones abierto",
            "murmur_watchman": "diente huevil con un vigilante de murmullos muy charlatán",
            "grumble_mail": "diente huevil con correo refunfuñón en la ventanilla",
        },
        "details": {
            "tiny_signature": "La reclamación lleva una firma pequeñita y muy seria.",
            "paper_counter": "La ventanilla del expediente está hecha de cartulina.",
            "tilted_glasses": "El encargado del cuaderno lleva las gafitas ladeadas.",
            "supper_margin": "En el margen he dibujado un sillón para el señor refunfuño.",
        },
    },
    "tummy": {
        "label": "tripita",
        "metaphors": {
            "spoon_orchestra": "tripita con una orquesta de cucharillas imaginarias",
            "complaint_notebook": "tripita con el cuaderno de protestas abierto",
            "grumble_radio": "tripita con una radio de refunfuños buscando emisora",
            "upside_down_sign": "tripita con el cartel de sobremesa puesto del revés",
            "paper_drum": "tripita con un tamborcito de papel ensayando sin público",
            "fussy_council": "tripita con un consejo de duendecillos quisquillosos",
            "murmur_theatre": "tripita con el teatro de murmullos en entreacto",
            "grumpy_clock": "tripita con un reloj de cuento que protesta por su horario",
        },
        "details": {
            "quiet_conductor": "La directora de la orquesta lleva zapatillas de fieltro dibujadas.",
            "paper_programme": "El programa del teatro trae una página de silencio.",
            "empty_stage": "El escenario de cartón tiene reservado un rato sin función.",
            "clock_note": "El reloj del expediente usa números con forma de patito.",
        },
    },
    "tiredness": {
        "label": "cansancio y plumitas",
        "metaphors": {
            "sunday_battery": "batería de pato en horario de domingo",
            "many_tuesdays": "plumaje con demasiados martes acumulados",
            "errand_suitcase": "patito con una maleta de recados que solicita vacaciones",
            "slow_typewriter": "plumitas con la máquina de escribir bostezo a bostezo",
            "nap_archive": "patito con el archivo de sobremesas pendiente de inaugurar",
            "pyjama_agenda": "plumitas con la agenda intentando ponerse el pijama",
            "late_office": "patito con la oficina de los «tengo que» abierta de más",
            "cloud_cushion": "plumaje con una nube de papel buscando cojín",
        },
        "details": {
            "closed_agenda": "La agenda del cuento acepta hoy páginas en blanco.",
            "slipper_stamp": "El sello del expediente lleva zapatillas y no tiene prisa.",
            "late_pencil": "Mi lápiz ha pedido permiso para quedarse detrás de la oreja.",
            "little_holiday": "En la esquina del papel cabe un domingo de bolsillo.",
        },
    },
    "affection": {
        "label": "afecto y mojo de Oso, entendido como compañía y mimos",
        "metaphors": {
            "hug_mailbox": "buzón de achuchones con sitio disponible",
            "company_reserve": "reserva de compañía con un sillón libre",
            "affection_post": "oficina del cariño con correspondencia bonita pendiente",
            "bear_constellation": "constelación de mimos con una estrella reservada al Oso",
            "ear_envelope": "sobre de orejitas con espacio para una nota amable",
            "cuddle_library": "biblioteca de achuchones con un préstamo por elegir",
            "gentle_guestbook": "libro de visitas del nido abierto por la página del cariño",
            "quiet_together": "tarde de patito con un huequito para compañía sin recados",
        },
        "details": {
            "optional_stamp": "El sello dice «solo si apetece» y tiene las orejitas torcidas.",
            "empty_chair": "El sillón de al lado acepta visitas y también ratitos de silencio.",
            "paper_heart": "En el sobre he dibujado un corazón que no pide nada a cambio.",
            "bear_signature": "La esquina para la firma del Oso se queda abierta, sin obligación.",
        },
    },
}

_LEGACY_DIAGNOSES = {
    "ruffled_feathers": "plumitas revueltas y nido pendiente de mimos",
    "tired_feathers": "batería de pato pidiendo una tarde de nido",
    "grumpy_beak": "pico refunfuñón y bufandita de cuento en busca de dueño",
    "grumpy_tummy": "tripita de pato con el día torcido",
    "busy_head": "cabecita de pato con demasiados cuacs en la agenda",
    "tired_wings": "alitas pidiendo permiso para dejar de aletear",
    "grumpy_webbing": "membranas de patita reclamando un nido mullido",
    "grumpy_egg_tooth": "diente huevil refunfuñón en el cuaderno de los patos",
    "cuddle_shortage": "reserva de achuchones por rellenar",
}
_LEGACY_FAMILIES = dict(zip(_LEGACY_DIAGNOSES, (
    "tiredness", "tiredness", "beak", "tummy", "head", "wings", "webbing", "egg_tooth", "affection")))
_LEGACY_CATEGORIES = {"mild_respiratory": "grumpy_beak", "ordinary_tiredness": "tired_feathers", "abdominal_pain": "grumpy_tummy"}
DIAGNOSES = {**_LEGACY_DIAGNOSES, **{
    f"{family}_{key}": text for family, catalog in DIAGNOSIS_FAMILIES.items()
    for key, text in catalog["metaphors"].items()
}}

# Keep these exact strings: summaries of earlier prescriptions use them too.
CARE = {
    "rest": "Deja los recados para otro rato y descansa, Patita. El sello de Salchicher dice «hoy las plumas libran».",
    "feathers": "Si te apetece, el Oso tiene una misión: alisar las plumitas con una caricia y dejar el nido bien mullido.",
    "comfort": "Un abrazo de perro de mi parte y, si quieres, un achuchón del Oso. El «mojo de oso» de esta receta son mimos imaginarios.",
    "blanket": "Elige tu rincón favorito y acomoda la mantita a tu gusto. Hoy el nido puede quedarse sin lista de tareas.",
    "food": "Si te apetece merendar, el Oso puede acercarte tu fruta favorita o un cuenquito de compota de manzana.",
    "fluids": "Una bandejita con un vaso de agua al alcance de la patita, para cuando te apetezca un sorbito.",
    "warm_drink": "Si te apetece, una tacita templada de tu bebida de siempre y un rato de conversación bajita.",
    "bath": "En nuestro cuento preparo una bañerita de agua templada y burbujas con forma de estrella para el patito de goma.",
}
_NEW_CARE = {
    "whisper_library": ("Biblioteca de susurros", "Si te apetece, elegimos un cuento cortito o nos quedamos en silencio; las dos opciones tienen carnet de biblioteca.", "rest"),
    "errand_retirement": ("Jubilación de recados", "Si hoy puedes, los recados que admitan espera se toman una tarde libre. Les dibujo un bastoncito de cartón y una pensión de domingo.", "rest"),
    "cushion_court": ("Tribunal del cojín favorito", "Puedes elegir tu rincón cómodo; yo le pongo un sello imaginario de aprobación, con una orejita por fuera.", "rest"),
    "ear_mail": ("Correo de orejitas", "Si quieres, te dejo una nota de cariño firmada con mi patita. No necesita respuesta.", "company"),
    "bear_relay": ("Relevo del Oso", "Si os apetece a los dos, puedes pedir al Oso compañía o ayuda con algún recado que pueda hacer por ti.", "company"),
    "silence_concert": ("Concierto de silencio", "Si te apetece, dejamos cerrada la agenda del cuento y pasamos un ratito tranquilo, sin tener que contar nada.", "rest"),
    "rubber_duck_embassy": ("Embajada de patitos de goma", "Si te hace gracia, imaginamos un desfile diminuto de patitos por mi escritorio; el embajador lleva un sombrero demasiado grande.", "play"),
    "no_merit_diploma": ("Diploma de no hacer méritos", "Puedes aceptar este diploma de cuento: el cariño no exige haber terminado nada. Yo lo firmo aunque el escritorio siga revuelto.", "company"),
    "paper_cloud_observatory": ("Observatorio de nubes de papel", "Si te apetece jugar, inventamos una nube y decidimos a qué animal se parece. También puede quedarse en nube y tan contenta.", "play"),
    "little_joy_archive": ("Archivo de pequeñas alegrías", "Puedes escoger una cosa agradable para recordar conmigo, o dejar el archivador cerrado y que te acompañe en silencio.", "company"),
    "chosen_blanket": ("Turno de manta elegida", "Si estás a gusto con ella, tu mantita favorita puede acompañar la escena. Tú eliges el rincón y cuándo pasar a otra cosa.", "rest"),
    "hug_audience": ("Audiencia de achuchón", "Si lo quieres y el Oso también, queda invitado un abrazo; también vale compañía sin contacto.", "company"),
    "clock_coatroom": ("Guardarropa de relojes de cuento", "Si te apetece imaginarlo, los relojes de mi consulta dejan sus sombreros en el perchero y charlan bajito. Tú no tienes que seguirles el ritmo.", "play"),
    "quiet_window": ("Palco de ventana imaginaria", "Podemos inventar una ventana que dé a un estanque tranquilo y dejar a un patito de papel vigilando las nubecitas.", "play"),
    "unfinished_page": ("Permiso de página sin acabar", "Si hoy te viene bien, algo que pueda esperar puede quedarse sin terminar. En mi cuaderno de cuento las páginas a medias también tienen sitio.", "rest"),
    "kind_word_ticket": ("Billete de palabra bonita", "Si te apetece, elegimos una frase amable para acompañar la tarde. Mi propuesta es: «Patita merece cariño también hoy».", "company"),
    "bear_postcard": ("Postal para el Oso", "Si quieres, imaginamos una postal que pida compañía a tu gusto: charla, silencio o un abrazo que os apetezca a los dos.", "company"),
    "duck_title": ("Nombramiento de Patita Ilustre", "Si te divierte, hoy te nombro inspectora honoraria de cojines de cuento. El cargo no trae tareas ni examen.", "play"),
    "pocket_sunday": ("Domingo de bolsillo", "Si te viene bien y puedes, guarda un ratito sin recados que puedan esperar. En el cuento lo llamamos domingo, aunque el calendario lleve otro sombrero.", "rest"),
    "small_story": ("Teatro de una sola frase", "Si te hace gracia, inventamos una historia cortita: un perro perdió su sello y descubrió que lo llevaba en la oreja. El público puede ser un cojín.", "play"),
    "affection_guestbook": ("Libro de visitas cariñosas", "Si quieres, dejamos escrito en el cuento que hoy has pasado por aquí y había un sillón para ti. No hace falta contar nada más.", "company"),
    "gentle_background": ("Radio de salón a tu gusto", "Si te apetece, puedes elegir un sonido que te resulte agradable o quedarte con el silencio. Tú llevas la programación de la tarde.", "rest"),
    "paper_medal": ("Medalla de estar aquí", "Si te divierte, te dibujo una medalla de papel con forma de patita. No premia aguantar ni hacer cosas: es un detalle de cariño.", "play"),
    "friendly_no": ("Sello de «hoy no me apetece»", "Si quieres, puedes dejar cualquier mimo de esta página para otro rato. Mi sello de perro aprueba también los descansos de las recetas.", "company"),
}
CARE.update({key: item[1] for key, item in _NEW_CARE.items()})
_CARE_NAMES = {
    "rest": "Permiso de tarde libre", "feathers": "Peinado de plumitas a petición",
    "comfort": "Correspondencia de achuchones", "blanket": "Reserva de nido favorito",
    "food": "Bandejita de merienda elegida", "fluids": "Ventanilla del sorbito opcional",
    "warm_drink": "Sobremesa de tacita y charla", "bath": "Escena del patito de goma",
    **{key: item[0] for key, item in _NEW_CARE.items()},
}
_CARE_GROUPS = {
    "rest": "rest", "feathers": "company", "comfort": "company", "blanket": "rest",
    "food": "snack", "fluids": "snack", "warm_drink": "snack", "bath": "play",
    **{key: item[2] for key, item in _NEW_CARE.items()},
}
CARE_FLOURISHES = {
    "paw_seal": "En el papel queda un sello torcido con forma de patita.",
    "ear_ribbon": "Le ato al expediente una cinta dibujada con orejitas de perro.",
    "bear_envelope": "El sobre de cuento lleva un dibujo del Oso sosteniendo una flor de papel.",
    "duck_witness": "Un patito de cartón hace de testigo y asiente con mucha solemnidad.",
    "moon_stamp": "El sello postal tiene una luna que bosteza con discreción.",
    "tiny_fanfare": "En la ilustración suena una fanfarria tan pequeña que solo mueve un bigote.",
    "sleepy_initials": "Mis iniciales salen un poco dormidas: la pluma se había puesto zapatillas.",
    "optional_ribbon": "La cinta del paquete dice «a tu gusto, sin obligación».",
}
_OPENINGS = {
    "notebook": "Me ajusto las gafitas y abro el cuaderno de los patos.",
    "stamp": "Saco mi sello de patita y aparto los recados del escritorio.",
    "chair": "Acerca esas plumitas al sillón; ya tengo el lápiz detrás de la oreja.",
    "spectacles": "Las gafitas se me resbalan un poquito, pero ya he encontrado la página del vademécum de los patos.",
    "bookmark": "Retiro del cuaderno un marcapáginas con forma de salchicha y pongo cara de perro estudioso.",
    "drawer": "Abro el cajón de los expedientes de plumas; el sello intenta esconderse debajo de mi oreja.",
    "ceremony": "Un momento de solemnidad perruna, Patita: he enderezado la bata y torcido el sello.",
    "paperclip": "Sujeto la página con un clip de patito y me aclaro el cuac; el mío sigue sonando a perro.",
}
_CLOSINGS = {
    "paw": "Firmado con una patita: Doctor Salchicher. ✧",
    "nest": "El nido queda oficialmente en modo mimo.",
    "bear": "Le pongo un sello al sobre para el Oso: «encargo de cariño, sin prisas».",
    "ear": "Firmo con solemnidad; la orejita que ha caído sobre el papel también cuenta como firma.",
    "drawer": "Guardo una copia imaginaria en el cajón de las cosas amables. La llave la lleva un patito de papel.",
    "permission": "Y queda aprobado cambiar de idea: en este cuaderno manda lo que te apetezca, Patita.",
    "glasses": "Doy por terminada la ceremonia y vuelvo a buscar las gafitas, que siguen en mi nariz.",
    "seal": "Sello de perro, borde de plumas y una esquina reservada para la firma de Patita.",
}


def _history_text(excluded: Any) -> str:
    """Accept previous rendered replies or chat history, never echo either."""
    if isinstance(excluded, (str, Mapping)):
        excluded = [excluded]
    if not isinstance(excluded, (list, tuple)):
        return ""
    texts = []
    for item in excluded[-24:]:
        if isinstance(item, Mapping):
            item = item.get("content") if item.get("role") == "assistant" else None
        if isinstance(item, str):
            texts.append(item[:16000])
    return "\n".join(texts)


def _available(catalog: dict[str, str], seen: str) -> dict[str, str]:
    return {key: text for key, text in catalog.items() if text not in seen} or dict(catalog)


def _pick(catalog: dict[str, str], preferred: Any, seen: str) -> str:
    available = _available(catalog, seen)
    if isinstance(preferred, str) and preferred in available:
        return preferred
    return _random.choice(list(available))


def _diagnosis(data: Mapping, seen: str) -> str:
    choice = data.get("diagnosis")
    if not isinstance(choice, (str, Mapping)) or (isinstance(choice, str) and choice not in DIAGNOSES):
        category = data.get("category")
        choice = _LEGACY_CATEGORIES.get(category) if isinstance(category, str) else None
    if isinstance(choice, str) and choice in DIAGNOSES:
        if DIAGNOSES[choice] not in seen:
            return DIAGNOSES[choice] + "."
        family = _LEGACY_FAMILIES.get(choice)
        if family is None:
            family = next((key for key in DIAGNOSIS_FAMILIES if choice.startswith(key + "_")), "tiredness")
        choice = {"family": family}
    if not isinstance(choice, Mapping):
        choice = {}
    family = choice.get("family")
    if not isinstance(family, str) or family not in DIAGNOSIS_FAMILIES:
        family = "tiredness"
    parts = DIAGNOSIS_FAMILIES[family]
    metaphor = _pick(parts["metaphors"], choice.get("metaphor"), seen)
    detail = _pick(parts["details"], choice.get("detail"), seen)
    result = parts["metaphors"][metaphor] + ". " + parts["details"][detail]
    if result in seen:
        # Once individual fragments have all appeared, still avoid repeating a
        # complete pairing while that family's other combinations are unused.
        alternatives = [base + ". " + end for base in parts["metaphors"].values()
                        for end in parts["details"].values() if base + ". " + end not in seen]
        if alternatives:
            result = _random.choice(alternatives)
    return result


def _care_choices(data: Mapping, seen: str) -> list[tuple[str, str | None]]:
    raw = data.get("care")
    selected = []
    requested = set()
    for item in raw[:16] if isinstance(raw, list) else []:
        key = item.get("id") if isinstance(item, Mapping) else item
        if not isinstance(key, str) or key not in CARE or key in requested:
            continue
        requested.add(key)
        # The selector knows the context: water must not turn into a snack, nor
        # quiet company into an embrace. Vary the ceremony, not this choice.
        flourish = item.get("flourish") if isinstance(item, Mapping) else None
        if not isinstance(flourish, str) or flourish not in CARE_FLOURISHES:
            flourish = None
        selected.append((key, flourish))
        if len(selected) == 4:
            break
    if not selected:
        for group_name in ("rest", "company", "play"):
            group = {key: text for key, text in CARE.items() if _CARE_GROUPS[key] == group_name}
            selected.append((_pick(group, None, seen), None))
    return selected


def render_storybook(data: Any, excluded: Any = None) -> str:
    """Render a validated recipe; unknown IDs and free prose never reach output.

    ``excluded`` may be recent chat history or a list of earlier rendered replies.
    Story diagnoses retain their anatomy; explicit care keeps its meaning.
    Legacy diagnosis/category and string care IDs remain accepted.
    """
    data = data if isinstance(data, Mapping) else {}
    seen = _history_text(excluded)
    opening = _OPENINGS[_pick(_OPENINGS, data.get("opening"), seen)]
    closing = _CLOSINGS[_pick(_CLOSINGS, data.get("closing"), seen)]
    lines = [opening, "", "Diagnóstico de cuento: " + _diagnosis(data, seen), "",
             "Mi receta para Patita. Tú eliges lo que te apetece; también vale dejarla para otro rato:"]
    for number, (key, flourish) in enumerate(_care_choices(data, seen), 1):
        line = f"{number}. {_CARE_NAMES[key]}: {CARE[key]}"
        if flourish is not None or number == 1:
            flourish = _pick(CARE_FLOURISHES, flourish, seen)
            decoration = CARE_FLOURISHES[flourish]
            line += " " + decoration
            seen += "\n" + decoration
        lines.append(line)
    lines.extend(("", closing))
    return "\n".join(lines)


def catalog_for_prompt(excluded: Any = None) -> dict[str, Any]:
    """Return fresh, JSON-compatible catalog data, preferring unused fragments."""
    seen = _history_text(excluded)
    # Refresh exhausted kinds separately, so using every companionship option
    # does not remove companionship while unrelated snacks remain unused.
    available_care = {}
    for group in dict.fromkeys(_CARE_GROUPS.values()):
        members = {key: text for key, text in CARE.items() if _CARE_GROUPS[key] == group}
        available_care.update(_available(members, seen))
    return {
        "diagnosis_families": {key: {"label": family["label"],
                                   "metaphors": _available(family["metaphors"], seen),
                                   "details": _available(family["details"], seen)}
                               for key, family in DIAGNOSIS_FAMILIES.items()},
        "legacy_diagnoses": dict(_LEGACY_DIAGNOSES),
        "care": {key: {"name": _CARE_NAMES[key], "text": text, "group": _CARE_GROUPS[key]}
                 for key, text in available_care.items()},
        "care_flourishes": _available(CARE_FLOURISHES, seen),
        "openings": _available(_OPENINGS, seen),
        "closings": _available(_CLOSINGS, seen),
    }
