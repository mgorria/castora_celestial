import json
import logging
import os
from typing import Any

from openai import AsyncOpenAI

from lore_utils import read_core_lore, read_recent_story_memory, read_relevant_character_lore


logger = logging.getLogger("control-castora.story_service")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2")

STORY_TYPE_GUIDE = """
Tipos de cuento que conviene rotar:
- viaje_suave: paseo, excursion pequena, mercado lejano, estacion antigua o camino que ya casi nadie pisa.
- anecdota_antigua: recuerdo de Mimosuga con Caparantonio, Tia Lironda u otro amigo de juventud.
- merienda_domestica: Cafe de las Miguitas, desayuno, bizcocho, taza, mesa pequena o normas de merienda.
- objeto_magico: manta, carta, cucharilla, chal, cuaderno, ventana, cajita o cosa domestica con magia suave.
- visita_inesperada: llega alguien cercano con un recado pequeno, una preocupacion tierna o una sorpresa.
- cuidado_y_abrigo: Brumilda, manta, tarde de lluvia, descanso, hogar y consuelo sin ponerse intenso.
- paseo_con_donetito: Donetito investiga algo pequeno, pero no debe usarse si ya aparecio recientemente.
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
) -> list[dict[str, str]]:
    lore = read_core_lore()
    recent_memory = read_recent_story_memory()
    prompt = f"""
Eres el sistema narrativo privado de Mimosuga. Devuelve SOLO JSON valido.

Contexto de lore:
{lore}

Narrador actual: {narrator}

Historias recientes que conviene no repetir:
{_recent_text(recent_summaries)}

Memoria reciente en Markdown:
{recent_memory}

Necesito dos opciones de cuento diario para Patita. Mimosuga es una tortuga abuela
magica, calida, tierna y tranquila. Las opciones deben ser cercanas, domesticas y
magicas. Nada oscuro, violento, sexual o perturbador. No menciones IA ni tecnologia.

{STORY_TYPE_GUIDE}

Reglas anti-repeticion:
- Las dos opciones deben ser claramente distintas entre si.
- No repitas personajes, estructura, conflicto domestico ni objeto central de los ultimos cuentos.
- No propongas el mismo tipo de cuento que se haya usado en los ultimos 2 cuentos.
- Una de las opciones debe abrir variedad estructural: viaje suave, anecdota antigua, visita inesperada u objeto magico. No hagas siempre cuento de merienda/desayuno.
- Si en los ultimos cuentos salieron Caparablanda, Donetito u Osito Castori, evita usarlos ahora salvo que sea imprescindible.
- Osito Castori, Oficina Castori, Castora Celestial, Plumadulce y Bambalin son apariciones especiales, no recursos cotidianos.
- Para cuentos cotidianos prefiere rotar entre Tia Lironda, Senora Migaja, Brumilda, Caparantonio, Caparablanda y Donetito, sin repetir siempre los mismos.
- Incluye con frecuencia viajes suaves y anecdotas antiguas de Mimosuga con Caparantonio, sin convertirlo siempre en aventura epica.

Formato JSON exacto:
{{
  "options": [
    {{"title": "titulo breve", "teaser": "descripcion tierna de 1 frase", "story_type": "uno de los tipos listados", "primary_characters": ["personaje"]}},
    {{"title": "titulo breve", "teaser": "descripcion tierna de 1 frase", "story_type": "otro tipo distinto", "primary_characters": ["personaje"]}}
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

Escribe un cuento completo para Patita contado por Mimosuga. Reglas:
- Tono calido, intimo, tierno y narrativo.
- Debe parecer que Mimosuga se lo cuenta directamente a Patita.
- Nunca uses el nombre humano de Patita.
- Nada oscuro, violento, sexual o perturbador.
- No menciones que eres IA.
- No uses moraleja explicita.
- No repitas siempre la misma estructura.
- Preferir detalles cotidianos magicos: desayunos, mantas, cartas, paseos,
  meriendas, ventanas, pequenas visitas, Brumilda, Senora Migaja, Tia Lironda,
  Caparantonio y sucesos tiernos.
- No repitas la estructura, personajes principales, objeto magico central ni situacion
  domestica de los ultimos cuentos.
- Respeta el story_type de la opcion elegida y haz que se note en la estructura.
- Si la opcion elegida es viaje_suave, debe haber desplazamiento real: camino, estacion, mercado, puente, senda o lugar nuevo.
- Si la opcion elegida es anecdota_antigua, debe sentirse como recuerdo de Mimosuga, con Caparantonio o Tia Lironda si encaja.
- Si la opcion elegida es objeto_magico, el objeto debe ser el centro narrativo y no solo decoracion.
- Si Caparablanda, Donetito u Osito Castori aparecieron en los ultimos cuentos, evita
  usarlos como protagonistas ahora.
- Osito Castori, Oficina Castori, Castora Celestial, Plumadulce y Bambalin deben aparecer
  rara vez y solo si la opcion elegida pide claramente un cuento especial.
- Longitud orientativa: 600 a 900 palabras.

Formato JSON exacto:
{{
  "title": "titulo del cuento",
  "full_text": "cuento completo",
  "summary": "resumen breve para memoria interna",
  "story_type": "tipo usado",
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
        "characters_used": data.get("characters_used") or [],
        "locations_used": data.get("locations_used") or [],
        "new_lore_proposals": data.get("new_lore_proposals") or [],
    }
