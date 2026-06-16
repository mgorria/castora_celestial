from pathlib import Path
from typing import Any
import os
import re


LORE_DIR = Path(__file__).parent / "lore"
PENDING_STORIES_DIR = Path(
    os.getenv("PENDING_STORIES_DIR", str(LORE_DIR / "historias" / "pendientes"))
)
RECENT_STORY_MEMORY_PATH = Path(
    os.getenv("RECENT_STORY_MEMORY_PATH", str(LORE_DIR / "historias" / "memoria-reciente.md"))
)
COURT_DIR = LORE_DIR / "corte"


def read_lore_file(relative_path: str) -> str:
    path = LORE_DIR / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_core_lore() -> str:
    resumen = read_lore_file("resumen-para-ia.md")
    reglas = read_lore_file("reglas-de-tono.md")
    continuidad = read_lore_file("continuidad-canonica.md")
    return (
        f"# Resumen de lore\n\n{resumen}\n\n"
        f"# Continuidad canonica\n\n{continuidad}\n\n"
        f"# Reglas de tono\n\n{reglas}"
    ).strip()


def read_court_lore() -> str:
    codigo = read_lore_file("corte/codigo-penal-pompones.md")
    jurisprudencia = read_lore_file("corte/jurisprudencia.md")
    jueces = read_lore_file("corte/jueces.md")
    return (
        "# Codigo Penal de Pompones y Plumas\n\n"
        f"{codigo or 'No hay codigo penal escrito todavia.'}\n\n"
        "# Perfiles de jueces\n\n"
        f"{jueces or 'No hay perfiles de jueces escritos todavia.'}\n\n"
        "# Jurisprudencia manual\n\n"
        f"{jurisprudencia or 'No hay jurisprudencia manual escrita todavia.'}"
    ).strip()


def read_court_judge_profile(case_id: int | str) -> dict[str, str]:
    content = read_lore_file("corte/jueces.md")
    if not content.strip():
        return {
            "name": "Sala Unica de Pompones y Plumas",
            "profile": "Juez colegiado, carinoso, proporcional y dispuesto a absolver si la prueba es floja.",
        }

    sections = re.split(r"(?m)^##\s+", content)
    profiles = []
    for section in sections:
        section = section.strip()
        if not section or section.startswith("#"):
            continue
        title, _, body = section.partition("\n")
        title = title.strip()
        body = body.strip()
        if title and body:
            profiles.append({"name": title, "profile": body})

    if not profiles:
        return {
            "name": "Sala Unica de Pompones y Plumas",
            "profile": content.strip(),
        }

    try:
        index = (int(case_id) - 1) % len(profiles)
    except (TypeError, ValueError):
        index = 0
    return profiles[index]


def read_recent_story_memory() -> str:
    if not RECENT_STORY_MEMORY_PATH.exists():
        return "No hay memoria reciente en Markdown."
    return RECENT_STORY_MEMORY_PATH.read_text(encoding="utf-8")


def parse_character_lore_file(path: Path) -> tuple[str, list[str], str]:
    content = path.read_text(encoding="utf-8")
    aliases = []
    title = path.stem.replace("-", " ").title()

    if content.startswith("---"):
        _, _, rest = content.partition("---")
        frontmatter, _, body = rest.partition("---")
        content = body.strip()
        current_key = None
        for raw_line in frontmatter.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("-") and current_key == "aliases":
                aliases.append(line[1:].strip().strip('"'))
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            current_key = key.strip()
            value = value.strip().strip('"')
            if current_key == "name" and value:
                title = value
            elif current_key == "aliases" and value and value != "[]":
                aliases.extend(item.strip().strip('"') for item in value.split(","))

    heading = re.search(r"^#\s+(.+)$", content, flags=re.MULTILINE)
    if heading:
        title = heading.group(1).strip()

    aliases.extend([title, path.stem.replace("-", " ")])
    aliases = [alias for alias in aliases if alias]
    return title, aliases, content


def discover_character_lore() -> list[dict[str, Any]]:
    character_dir = LORE_DIR / "personajes"
    if not character_dir.exists():
        return []
    characters = []
    for path in sorted(character_dir.glob("*.md")):
        title, aliases, content = parse_character_lore_file(path)
        characters.append(
            {
                "title": title,
                "aliases": aliases,
                "content": content,
                "path": path,
            }
        )
    return characters


def read_relevant_character_lore(text: str) -> str:
    lowered = text.lower()
    sections = []
    seen_paths = set()
    for character in discover_character_lore():
        path = character["path"]
        if path in seen_paths:
            continue
        if not any(alias.lower() in lowered for alias in character["aliases"]):
            continue
        sections.append(f"## {character['title']}\n\n{character['content']}")
        seen_paths.add(path)

    if not sections:
        return "No se han detectado fichas concretas de personajes para esta opcion."
    return "\n\n".join(sections)


def safe_slug(value: str) -> str:
    allowed = []
    for char in value.lower():
        if char.isalnum():
            allowed.append(char)
        elif char in {" ", "-", "_"}:
            allowed.append("-")
    slug = "".join(allowed).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "cuento"


def write_pending_story_markdown(story: dict[str, Any]) -> Path:
    PENDING_STORIES_DIR.mkdir(parents=True, exist_ok=True)
    created_at = story["created_at"].date().isoformat() if story.get("created_at") else ""
    filename = f"{story['id']:04d}-{safe_slug(story['title'])}.md"
    path = PENDING_STORIES_DIR / filename
    proposals = story.get("new_lore_proposals") or []
    proposals_text = "\n".join(f"- {item}" for item in proposals) or "- Ninguno"

    content = (
        "---\n"
        f"id: {story['id']}\n"
        f"title: \"{story['title']}\"\n"
        f"status: {story['status']}\n"
        f"narrator: {story['narrator']}\n"
        f"created_at: {created_at}\n"
        "delivered_to: Patita\n"
        "---\n\n"
        f"# {story['title']}\n\n"
        f"{story['full_text']}\n\n"
        "## Resumen\n\n"
        f"{story['summary']}\n\n"
        "## Elementos nuevos propuestos\n\n"
        f"{proposals_text}\n"
    )
    path.write_text(content, encoding="utf-8")
    return path


def write_recent_story_memory_markdown(stories: list[dict[str, Any]]) -> Path:
    RECENT_STORY_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Memoria reciente de cuentos",
        "",
        "Este archivo resume los ultimos cuentos entregados para evitar repeticiones.",
        "No es canon por si mismo; es memoria operativa para la IA.",
        "",
    ]
    if not stories:
        lines.append("No hay cuentos recientes registrados.")
    for story in stories:
        characters = story.get("characters_used") or []
        locations = story.get("locations_used") or []
        if not isinstance(characters, list):
            characters = []
        if not isinstance(locations, list):
            locations = []
        created_at = story.get("created_at")
        created_text = created_at.date().isoformat() if hasattr(created_at, "date") else ""
        lines.extend(
            [
                f"## {story.get('title', 'Sin titulo')}",
                "",
                f"- ID: {story.get('id', '')}",
                f"- Fecha: {created_text}",
                f"- Opcion elegida: {story.get('selected_option') or ''}",
                f"- Tipo: {selected_story_type(story)}",
                f"- Forma: {selected_story_meta(story, 'narrative_shape')}",
                f"- Pulso: {selected_story_meta(story, 'emotional_tone')}",
                f"- Personajes: {', '.join(str(item) for item in characters) or 'No registrados'}",
                f"- Lugares: {', '.join(str(item) for item in locations) or 'No registrados'}",
                f"- Resumen: {story.get('summary', '')}",
                "",
            ]
        )
    RECENT_STORY_MEMORY_PATH.write_text("\n".join(lines), encoding="utf-8")
    return RECENT_STORY_MEMORY_PATH


def selected_story_type(story: dict[str, Any]) -> str:
    return selected_story_meta(story, "story_type")


def selected_story_meta(story: dict[str, Any], key: str) -> str:
    selected_option = story.get("selected_option")
    offered_options = story.get("offered_options") or []
    if isinstance(offered_options, list):
        for option in offered_options:
            if isinstance(option, dict) and option.get("title") == selected_option:
                return str(option.get(key) or "No registrado")
    return "No registrado"
