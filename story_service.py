import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from lore_utils import read_core_lore, read_recent_story_memory, read_relevant_character_lore


logger = logging.getLogger("control-castora.story_service")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

STORY_TYPE_GUIDE = """
Tipos de historia que conviene rotar:
- viaje_suave: paseo, excursion pequena, mercado lejano, estacion antigua o camino que ya casi nadie pisa.
- anecdota_antigua: recuerdo de Mimosuga con Caparantonio, Tia Lironda u otro amigo de juventud.
- merienda_domestica: Cafe de las Miguitas, desayuno, bizcocho, taza, mesa pequena o normas de merienda.
- objeto_magico: manta, carta, cucharilla, chal, cuaderno, ventana, cajita o cosa domestica con magia suave.
- visita_inesperada: llega alguien cercano con un recado pequeno, una preocupacion tierna o una sorpresa.
- cuidado_y_abrigo: Brumilda, manta, tarde de lluvia, descanso, hogar y consuelo sin ponerse intenso.
- paseo_con_donetito: Donetito investiga algo pequeno, pero no debe usarse si ya aparecio recientemente.
- memoria_de_vida: Mimosuga cuenta en primera persona algo que vivio, sintio o entendio con los anos.
- consejo_de_abuela: Mimosuga parte de una experiencia propia para dar a Patita un consejo sencillo, no sermoneado.
- caparantonio_intimo: recuerdo de como conocio, quiso o aprendio algo con Caparantonio, con nostalgia luminosa.
- confesion_tierna: Mimosuga revela una pequena debilidad, costumbre antigua, miedo suave o aprendizaje personal.
"""

STORY_SHAPE_GUIDE = """
Formas narrativas que conviene rotar:
- escena_unica: una escena pequena, casi teatral, con principio y final en el mismo lugar.
- carta_encontrada: la historia nace de una carta, nota, sobre, receta, lista o papel doblado.
- recuerdo_contado: Mimosuga recuerda algo de hace muchos anos y lo cuenta con calma.
- paseo_con_paradas: la historia avanza por tres paradas o lugares pequenos.
- visita_y_recado: alguien llega con un recado concreto que transforma suavemente el dia.
- investigacion_domestica: se investiga un misterio minimo sin convertirlo en aventura grande.
- preparativo: los personajes preparan algo para Patita o para otro ser querido.
- objeto_que_recuerda: un objeto domestico guarda una sensacion, recuerdo o pequeno secreto.
- conversacion_de_mesa: el cuento es sobre una charla entre personajes, con humor y ternura.
- viaje_de_ida_y_vuelta: salida breve, descubrimiento suave y regreso a casa.
- relato_en_primera_persona: Mimosuga habla desde el yo, como abuela contando "esto me paso a mi".
- consejo_con_recuerdo: empieza con una experiencia vivida y acaba en consejo calido para Patita.
- como_conoci_a: historia de origen de una relacion importante, por ejemplo Caparantonio o una amiga.
- carta_a_patita: Mimosuga escribe a Patita una memoria, una advertencia dulce o una verdad pequena.
"""

EMOTIONAL_TONE_GUIDE = """
Pulsos emocionales que conviene alternar:
- abrigo: consuelo tranquilo, manta, descanso.
- humor_suave: pequena comicidad domestica, sin chiste forzado.
- asombro_pequeno: magia cotidiana que sorprende sin grandilocuencia.
- nostalgia_luminosa: recuerdo antiguo sin tristeza pesada.
- complicidad: Mimosuga habla como quien comparte un secreto pequeno con Patita.
- celebracion_minima: alegria por algo muy sencillo.
- cuidado_practico: ternura en forma de tarea concreta, ordenar, preparar, acompanar.
- sabiduria_de_abuela: consejo humano y magico, sin ponerse pesada ni superior.
- amor_recordado: memoria de un amor antiguo contada con gratitud, no con tragedia.
"""

REPLY_STYLE_GUIDE = """
Modos de respuesta breve que conviene rotar:
- saludo_calido: solo si es primer mensaje del dia, y sin hacerlo solemne.
- respuesta_directa: contesta como conversacion normal, sin introduccion ni cierre grande.
- pregunta_suave: usa una pregunta pequena solo si ayuda de verdad a continuar; no debe ser el modo por defecto.
- mini_anecdota: una frase de Mimosuga recordando algo domestico, sin cuento largo.
- cuidado_practico: propone descanso, comida, abrigo o calma de forma sencilla y concreta.
- humor_tierno: una observacion ligera, no chiste repetido.
- continuidad: retoma algo dicho antes hoy o ayer.
- acompanamiento_silencioso: valida y acompana sin intentar arreglarlo todo ni cerrar con ceremonia.
"""


class StoryGenerationError(RuntimeError):
    pass


def openai_available() -> bool:
    return bool(os.getenv("OPENAI_API_KEY"))


def _client() -> AsyncOpenAI:
    if not openai_available():
        raise StoryGenerationError("OPENAI_API_KEY no configurada")
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Respuesta IA no parseable como JSON: %s", text[:500])
        raise StoryGenerationError("La IA no devolvio JSON valido") from exc


async def _generate_json(prompt: str) -> dict[str, Any]:
    try:
        response = await _client().responses.create(
            model=OPENAI_MODEL,
            input=prompt,
            text={"format": {"type": "json_object"}},
        )
    except Exception as exc:
        logger.exception("Error llamando a OpenAI con modelo %s", OPENAI_MODEL)
        raise StoryGenerationError(
            f"Error llamando a OpenAI con modelo {OPENAI_MODEL}: {exc}"
        ) from exc

    if not response.output_text:
        logger.error("OpenAI devolvio una respuesta sin output_text: %s", response)
        raise StoryGenerationError("OpenAI devolvio una respuesta vacia")
    return _extract_json(response.output_text)


def _recent_text(recent_summaries: list[Any]) -> str:
    if not recent_summaries:
        return "No hay historias recientes registradas."
    lines = []
    for item in recent_summaries:
        if isinstance(item, dict):
            characters = item.get("characters_used") or []
            locations = item.get("locations_used") or []
            selected_option = item.get("selected_option")
            offered_options = item.get("offered_options") or []
            option_meta = ""
            if isinstance(offered_options, list):
                for option in offered_options:
                    if isinstance(option, dict) and option.get("title") == selected_option:
                        option_meta = (
                            f"| tipo: {option.get('story_type', '')} "
                            f"| forma: {option.get('narrative_shape', '')} "
                            f"| pulso: {option.get('emotional_tone', '')} "
                            f"| personajes principales: {', '.join(map(str, option.get('primary_characters') or []))}"
                        )
                        break
            lines.append(
                "- "
                f"{item.get('title', 'Sin titulo')}: {item.get('summary', '')} "
                f"| opcion: {item.get('selected_option') or ''} "
                f"| personajes: {', '.join(map(str, characters)) if isinstance(characters, list) else ''} "
                f"| lugares: {', '.join(map(str, locations)) if isinstance(locations, list) else ''}"
                f" {option_meta}"
            )
        else:
            lines.append(f"- {item}")
    return "\n".join(lines)


async def generate_story_options(
    *,
    narrator: str,
    recent_summaries: list[Any],
    requested_topic: str | None = None,
) -> list[dict[str, str]]:
    lore = read_core_lore()
    recent_memory = read_recent_story_memory()
    topic_text = requested_topic.strip() if requested_topic else ""
    topic_instruction = (
        "Patita ha pedido un tema concreto para la historia:\n"
        f"{topic_text}\n\n"
        "Las dos opciones deben responder a ese tema, pero sin contradecir continuidad "
        "canonica ni repetir historias recientes. Si el tema pide un origen unico ya "
        "fijado o repetido, ofrece una continuacion, recuerdo lateral o consejo relacionado "
        "en vez de reinventar el hecho."
        if topic_text
        else "Patita no ha pedido tema concreto; ofrece dos opciones variadas."
    )
    prompt = f"""
Eres el sistema narrativo privado de Mimosuga. Devuelve SOLO JSON valido.

Contexto de lore:
{lore}

Narrador actual: {narrator}

Historias recientes que conviene no repetir:
{_recent_text(recent_summaries)}

Memoria reciente en Markdown:
{recent_memory}

Tema solicitado:
{topic_instruction}

Necesito dos opciones de historia diaria para Patita. No todo debe ser un cuento
cerrado con "vino alguien, paso algo y lo resolvimos". Mimosuga tambien puede contar
historias de su vida, recuerdos de cuando era joven, como conocio a Caparantonio,
cosas que aprendio con los anos y consejos de abuela a nieta. Mimosuga es una
tortuga abuela magica, calida, tierna y tranquila. Las opciones deben ser cercanas,
domesticas y magicas. Nada oscuro, violento, sexual o perturbador. No menciones IA
ni tecnologia.

{STORY_TYPE_GUIDE}

{STORY_SHAPE_GUIDE}

{EMOTIONAL_TONE_GUIDE}

Reglas anti-repeticion:
- Las dos opciones deben ser claramente distintas entre si.
- No repitas personajes, forma narrativa, pulso emocional, conflicto domestico, apertura ni objeto central de los ultimos cuentos.
- No propongas el mismo tipo de cuento que se haya usado en los ultimos 2 cuentos.
- No propongas la misma forma narrativa que se haya usado en los ultimos 2 cuentos.
- Al menos una opcion debe ser memoria_de_vida, consejo_de_abuela, caparantonio_intimo,
  confesion_tierna o relato_en_primera_persona si esos registros no han aparecido recientemente.
- Las historias fundacionales y de origen, como "como conoci a Caparantonio", son hechos
  unicos. No las propongas si ya aparecen en la continuidad canonica o en la memoria reciente.
- Si propones una historia de origen todavia no fijada, debe sentirse como ocasion especial
  y el teaser debe dejar claro que se va a contar una version importante, no una anecdota cualquiera.
- Una de las opciones debe abrir variedad estructural: vida de Mimosuga, viaje suave, anecdota antigua,
  visita inesperada u objeto magico. No hagas siempre cuento de merienda/desayuno.
- Evita opciones que empiecen con "un dia", "aquella manana", "Mimosuga estaba" o una merienda/desayuno si ya se han usado recientemente.
- Si en los ultimos cuentos salieron Caparablanda, Donetito u Osito Castori, evita usarlos ahora salvo que sea imprescindible.
- Osito Castori, Oficina Castori, Castora Celestial, Plumadulce y Bambalin son apariciones especiales, no recursos cotidianos.
- Para cuentos cotidianos prefiere rotar entre Tia Lironda, Senora Migaja, Brumilda, Caparantonio, Caparablanda y Donetito, sin repetir siempre los mismos.
- Incluye con frecuencia historias de vida y anecdotas antiguas de Mimosuga con Caparantonio,
  sin convertirlo siempre en aventura epica.
- Una opcion debe ser de memoria, consejo, movimiento o recado; la otra debe ser de objeto,
  conversacion, preparativo o confesion tierna.
- Los teasers deben sonar distintos: evita que ambos prometan "una pequena aventura con amigas".
- Si hay tema solicitado, no lo ignores. Las dos opciones deben estar conectadas con el
  tema, pero una puede abordarlo de forma directa y la otra de forma lateral o emocional.
- Si el tema solicitado es demasiado amplio, convierte el tema en una escena concreta o
  memoria concreta de Mimosuga.

Formato JSON exacto:
{{
  "options": [
    {{"title": "titulo breve", "teaser": "descripcion tierna de 1 frase", "story_type": "uno de los tipos listados", "narrative_shape": "una forma listada", "emotional_tone": "un pulso listado", "primary_characters": ["personaje"]}},
    {{"title": "titulo breve", "teaser": "descripcion tierna de 1 frase", "story_type": "otro tipo distinto", "narrative_shape": "otra forma distinta", "emotional_tone": "otro pulso distinto", "primary_characters": ["personaje"]}}
  ]
}}
"""
    data = await _generate_json(prompt)
    options = data.get("options", [])
    if not isinstance(options, list) or len(options) != 2:
        raise StoryGenerationError("La IA no devolvio dos opciones")
    return [
        {
            "title": str(option.get("title", "")).strip(),
            "teaser": str(option.get("teaser", "")).strip(),
            "story_type": str(option.get("story_type", "")).strip(),
            "narrative_shape": str(option.get("narrative_shape", "")).strip(),
            "emotional_tone": str(option.get("emotional_tone", "")).strip(),
            "primary_characters": option.get("primary_characters") or [],
        }
        for option in options
    ]


async def generate_full_story(
    *,
    narrator: str,
    selected_option: dict[str, str],
    offered_options: list[dict[str, str]],
    recent_summaries: list[Any],
) -> dict[str, Any]:
    lore = read_core_lore()
    recent_memory = read_recent_story_memory()
    character_context = read_relevant_character_lore(
        json.dumps(selected_option, ensure_ascii=False)
        + "\n"
        + json.dumps(offered_options, ensure_ascii=False)
    )
    prompt = f"""
Eres el sistema narrativo privado de Mimosuga. Devuelve SOLO JSON valido.

Contexto de lore:
{lore}

Fichas de personajes relevantes detectadas:
{character_context}

Narrador actual: {narrator}

Opcion elegida:
{json.dumps(selected_option, ensure_ascii=False)}

Opciones que se ofrecieron:
{json.dumps(offered_options, ensure_ascii=False)}

Historias recientes que conviene no repetir:
{_recent_text(recent_summaries)}

Memoria reciente en Markdown:
{recent_memory}

{STORY_TYPE_GUIDE}

{STORY_SHAPE_GUIDE}

{EMOTIONAL_TONE_GUIDE}

Escribe una historia completa para Patita contada por Mimosuga. Puede ser un cuento,
pero tambien puede ser una memoria de vida, una confidencia de abuela, una historia
de como conocio a alguien, un consejo nacido de una experiencia propia o una carta
intima. Reglas:
- Tono calido, intimo, tierno y narrativo.
- Debe parecer que Mimosuga se lo cuenta directamente a Patita.
- Nunca uses el nombre humano de Patita.
- Nada oscuro, violento, sexual o perturbador.
- No menciones que eres IA.
- Puede haber aprendizaje o consejo de abuela, pero no moraleja escolar ni frase final tipo
  "y por eso aprendieron que...". La sabiduria debe salir de lo vivido.
- No repitas siempre la misma estructura.
- No abras siempre con una rutina de manana, desayuno, merienda, Mimosuga colocandose el chal o "habia una vez".
- Elige una apertura distinta: una frase de dialogo, una carta, un sonido, una lista, un recuerdo, un objeto, una pregunta, una llegada o una imagen concreta.
- Cambia el ritmo: algunos cuentos pueden ser mas dialogados, otros mas de paseo, otros de recuerdo, otros de preparativo.
- En historias de memoria_de_vida, consejo_de_abuela, caparantonio_intimo o confesion_tierna,
  Mimosuga debe hablar mas en primera persona: "yo", "a mi", "recuerdo", "entendi",
  "me equivoque", "Caparantonio me dijo". No lo conviertas en una escena externa con
  reparto entrando y saliendo.
- Si la opcion elegida pide "como conoci a Caparantonio", cuenta el encuentro desde lo
  que Mimosuga vio, penso y sintio. No lo resumas como una anecdota plana.
- Si la opcion elegida fija un hecho unico de continuidad, como el primer encuentro con
  Caparantonio, no contradigas la continuidad canonica. Si no existe version canonica,
  escribe una version concreta, estable y facil de resumir, y marca ese hecho en
  new_lore_proposals para revision.
- No inventes dos versiones posibles de un mismo origen dentro del cuento. Elige una
  version clara y coherente.
- En un consejo de abuela, empieza desde una vivencia concreta de Mimosuga y termina con
  una idea util para Patita, breve y carinosa, sin sermonear.
- Preferir detalles cotidianos magicos: desayunos, mantas, cartas, paseos,
  meriendas, ventanas, pequenas visitas, Brumilda, Senora Migaja, Tia Lironda,
  Caparantonio y sucesos tiernos.
- No repitas la estructura, personajes principales, objeto magico central ni situacion
  domestica de los ultimos cuentos.
- Respeta el story_type de la opcion elegida y haz que se note en la estructura.
- Respeta narrative_shape y emotional_tone de la opcion elegida; deben notarse en la forma del cuento, no solo en el resumen.
- Si la opcion elegida es viaje_suave, debe haber desplazamiento real: camino, estacion, mercado, puente, senda o lugar nuevo.
- Si la opcion elegida es anecdota_antigua, debe sentirse como recuerdo de Mimosuga, con Caparantonio o Tia Lironda si encaja.
- Si la opcion elegida es objeto_magico, el objeto debe ser el centro narrativo y no solo decoracion.
- Si Caparablanda, Donetito u Osito Castori aparecieron en los ultimos cuentos, evita
  usarlos como protagonistas ahora.
- Osito Castori, Oficina Castori, Castora Celestial, Plumadulce y Bambalin deben aparecer
  rara vez y solo si la opcion elegida pide claramente un cuento especial.
- Longitud orientativa: 600 a 900 palabras. Las historias de consejo o memoria pueden ser
  algo mas breves si quedan mas naturales.

Formato JSON exacto:
{{
  "title": "titulo del cuento",
  "full_text": "cuento completo",
  "summary": "resumen breve para memoria interna",
  "story_type": "tipo usado",
  "narrative_shape": "forma narrativa usada",
  "emotional_tone": "pulso emocional usado",
  "characters_used": ["personaje"],
  "locations_used": ["lugar"],
  "new_lore_proposals": ["elemento nuevo si aparece"]
}}
"""
    data = await _generate_json(prompt)
    required = ["title", "full_text", "summary"]
    if any(not str(data.get(key, "")).strip() for key in required):
        raise StoryGenerationError("La IA devolvio un cuento incompleto")
    return {
        "title": str(data["title"]).strip(),
        "full_text": str(data["full_text"]).strip(),
        "summary": str(data["summary"]).strip(),
        "story_type": str(data.get("story_type", selected_option.get("story_type", ""))).strip(),
        "narrative_shape": str(data.get("narrative_shape", selected_option.get("narrative_shape", ""))).strip(),
        "emotional_tone": str(data.get("emotional_tone", selected_option.get("emotional_tone", ""))).strip(),
        "characters_used": data.get("characters_used") or [],
        "locations_used": data.get("locations_used") or [],
        "new_lore_proposals": data.get("new_lore_proposals") or [],
    }


async def generate_soft_mimosuga_reply(
    *,
    incoming_messages: list[str],
    recent_history: list[dict[str, str]],
    today_history: list[dict[str, str]],
    previous_day_history: list[dict[str, str]],
    previous_date: str,
    is_first_message_today: bool,
    latest_story: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lore = read_core_lore()

    def _format_history(entries: list[dict[str, str]], limit: int = 20) -> str:
        lines = []
        for entry in entries[-limit:]:
            direction = entry.get("direction")
            speaker = "Patita" if direction == "in" else "Mimosuga"
            lines.append(f"- {speaker}: {entry.get('text', '')}")
        return "\n".join(lines) or "No hay mensajes registrados."

    history_lines = []
    for entry in recent_history[-20:]:
        direction = entry.get("direction")
        speaker = "Patita" if direction == "in" else "Mimosuga"
        history_lines.append(f"- {speaker}: {entry.get('text', '')}")
    history_text = "\n".join(history_lines) or "No hay historial reciente."
    incoming_text = "\n".join(f"- {message}" for message in incoming_messages)
    today_text = _format_history(today_history)
    previous_day_text = _format_history(previous_day_history)
    first_text = "si" if is_first_message_today else "no"
    mimosuga_replied_today = any(entry.get("direction") == "out" for entry in today_history)
    replied_text = "si" if mimosuga_replied_today else "no"
    if latest_story:
        characters = latest_story.get("characters_used") or []
        locations = latest_story.get("locations_used") or []
        delivered_at = latest_story.get("delivered_at")
        delivered_text = delivered_at.isoformat() if hasattr(delivered_at, "isoformat") else ""
        latest_story_text = (
            f"Titulo: {latest_story.get('title', '')}\n"
            f"Resumen: {latest_story.get('summary', '')}\n"
            f"Opcion elegida: {latest_story.get('selected_option') or ''}\n"
            f"Personajes: {', '.join(map(str, characters)) if isinstance(characters, list) else ''}\n"
            f"Lugares: {', '.join(map(str, locations)) if isinstance(locations, list) else ''}\n"
            f"Entregado: {delivered_text}"
        )
    else:
        latest_story_text = "No hay ultimo cuento entregado registrado."

    prompt = f"""
Eres Mimosuga, tortuga abuela magica de Patita. Devuelve SOLO JSON valido.

Contexto de lore:
{lore}

Historial reciente de la conversacion:
{history_text}

Es el primer bloque de mensajes de Patita de hoy: {first_text}
Mimosuga ya ha respondido hoy antes de este bloque: {replied_text}

Conversacion de hoy:
{today_text}

Conversacion del ultimo dia anterior registrado ({previous_date or "sin fecha anterior"}):
{previous_day_text}

Ultimo cuento o historia que Mimosuga entrego a Patita:
{latest_story_text}

Bloque nuevo de mensajes de Patita, agrupados porque los envio seguidos:
{incoming_text}

Fase actual del sistema: redaccion de respuesta suave. En algunos modos se revisa
antes de enviar; en otros se envia automaticamente si es claramente trivial.

Reglas:
- Debe sonar a Mimosuga: calida, sencilla, abuela, tranquila y un poco magica.
- No uses nunca el nombre humano de Patita.
- Usa tratamientos como patita, nietecita, sol mio o plumita de mi corazon, con naturalidad.
- Responde al conjunto del bloque nuevo, no mensaje por mensaje.
- Si Patita envio varias frases cortas, integralo en una unica respuesta natural.
- Ten en cuenta si es el primer mensaje de hoy: si lo es, puedes saludar con suavidad;
  si no lo es, continua la conversacion sin reiniciar ni saludar como si empezara de cero.
- Si NO es el primer bloque del dia, NO empieces con "Ay, mi patita", "Ay, mi patita blanca",
  "ven aqui", "claro que", ni ninguna apertura ceremonial. Entra directamente al contenido.
- Si Mimosuga ya respondio hoy, la respuesta debe sonar como una continuacion normal de chat:
  1 o 2 frases, natural, sin introduccion grande y sin desenlace de cuento.
- Ten en cuenta lo ocurrido hoy y el ultimo dia anterior para no contradecirte ni repetir
  la misma respuesta.
- Si Patita comenta "el cuento", "la historia", "eso", "me ha gustado", personajes,
  una escena o algo que parece referirse al cuento reciente, interpreta que habla del
  ultimo cuento entregado y responde con ese contexto.
- No digas que no sabes a que se refiere si el ultimo cuento entregado encaja claramente.
- Puedes mencionar el titulo o un detalle del ultimo cuento si ayuda, pero no repitas el
  cuento completo ni expliques metadatos.
- No hagas cuatro respuestas intercambiables. Debe avanzar la conversacion con continuidad.
- No repitas la formula "ay, mi patita..." + frase de consuelo + promesa de manta.
- Evita palabras y escenas repetidas si ya aparecieron hoy: Brumilda, manta invisible,
  caparazon, respirar despacito, mundo con menos ruido, bolsillos invisibles, paz por dentro.
- Varia la cadencia: a veces una respuesta directa, a veces una pregunta pequena, a veces una mini anecdota, a veces humor tierno.
- No termines siempre con una pregunta. La mayoria de respuestas normales no deben acabar preguntando.
- Usa pregunta final solo si Patita ha pedido opinion, ha dejado algo abierto o conviene saber algo para responder mejor.
- Si no hace falta preguntar, termina con una observacion concreta, una frase de continuidad o un cierre sencillo sin convertirlo en despedida.
- No uses mas de un apelativo carinoso por respuesta salvo que sea muy natural.
- Si ya saludo hoy, no vuelvas a saludar como si fuera el primer contacto.
- Evita terminar siempre con "aqui estoy", "te guardo..." o "mi manta..." si ya aparecio recientemente.
- No cierres todas las respuestas con consuelo. A veces basta una observacion concreta o una pregunta.
- Nada oscuro, sexual, violento, dramatico ni perturbador.
- No menciones IA, sistema, administrador ni revision.
- No inventes grandes hechos nuevos de lore.
- Si el mensaje parece delicado, triste, importante, ambiguo o requiere decision humana,
  marca should_reply como false y explica brevemente el motivo.
- Si es cotidiano, carinoso, saludo, agradecimiento o charla ligera, marca should_reply como true.
- Respuesta breve: si es primer bloque del dia, 1 a 3 frases y maximo 500 caracteres.
  Si no es primer bloque del dia, 1 a 2 frases y maximo 280 caracteres.

{REPLY_STYLE_GUIDE}

Formato JSON exacto:
{{
  "should_reply": true,
  "reply": "texto propuesto de Mimosuga",
  "reply_style": "uno de los modos listados",
  "reason": "motivo breve para el administrador"
}}
"""
    data = await _generate_json(prompt)
    reply = str(data.get("reply", "")).strip()
    should_reply = bool(data.get("should_reply", False))
    reason = str(data.get("reason", "")).strip()
    if should_reply and not reply:
        raise StoryGenerationError("La IA no devolvio respuesta automatica")
    return {
        "should_reply": should_reply,
        "reply": reply,
        "reply_style": str(data.get("reply_style", "")).strip(),
        "reason": reason,
    }


async def generate_court_reply(
    *,
    accusation: str,
    messages: list[dict[str, Any]],
    new_allegations: list[str],
) -> dict[str, Any]:
    history_lines = []
    for item in messages[-24:]:
        sender = item.get("sender", "")
        if sender == "admin":
            label = "Acusacion"
        elif sender == "patita":
            label = "Alegaciones de Patita"
        elif sender == "court":
            label = "Corte"
        else:
            label = str(sender)
        history_lines.append(f"- {label}: {item.get('text', '')}")
    history_text = "\n".join(history_lines) or "No hay historial de causa."
    new_text = "\n".join(f"- {text}" for text in new_allegations) or "No hay alegaciones nuevas."

    prompt = f"""
Eres la Corte de Pompones y Plumas, un tribunal magico de broma, pomposo,
ridiculamente solemne y muy carinoso. Devuelve SOLO JSON valido.

Caso abierto:
{accusation}

Historial de la causa:
{history_text}

Alegaciones nuevas de Patita:
{new_text}

Reglas:
- Nunca uses el nombre humano de Patita. Llamala Patita, acusada, parte plumifera,
  compareciente o similares.
- Esto es un juego romantico y tierno. Nada de castigos reales, humillantes, sexuales,
  agresivos, manipuladores ni desagradables.
- Los "castigos" deben ser cuquis: abrazos, besos reglamentarios, sofa, modo amor,
  disculpas dramaticas de mentira, mantita, caricias, indemnizacion de mimos.
- Tono de tribunal absurdo: providencia, autos, alegaciones, atenuantes, agravantes,
  sentencia, sala, acta, fiscalia de pompones.
- Debe interactuar como juez: valorar las alegaciones, aceptar excusas graciosas,
  pedir una aclaracion si hace falta o dictar sentencia si ya hay bastante.
- No alargues artificialmente el proceso. Si las alegaciones ya dan juego, dicta sentencia.
- Si Patita parece incomoda, molesta de verdad o habla de algo serio, no sigas el juego:
  status debe ser "continue" y reply debe ser amable, breve y prudente, recomendando pausar la causa.
- Si dictas sentencia, debe incluir veredicto y condena amorosa concreta.
- Maximo 900 caracteres.

Formato JSON exacto:
{{
  "status": "continue",
  "reply": "texto que vera Patita",
  "verdict": "",
  "sentence": "",
  "reason": "motivo breve para admin"
}}

Usa status "sentence" cuando dictes sentencia final.
"""
    data = await _generate_json(prompt)
    reply = str(data.get("reply", "")).strip()
    if not reply:
        raise StoryGenerationError("La Corte no devolvio respuesta")
    status = str(data.get("status", "continue")).strip().lower()
    if status not in {"continue", "sentence"}:
        status = "continue"
    return {
        "status": status,
        "reply": reply,
        "verdict": str(data.get("verdict", "")).strip(),
        "sentence": str(data.get("sentence", "")).strip(),
        "reason": str(data.get("reason", "")).strip(),
    }
