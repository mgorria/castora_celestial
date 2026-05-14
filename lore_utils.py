from pathlib import Path
from typing import Any
import os


LORE_DIR = Path(__file__).parent / "lore"
PENDING_STORIES_DIR = Path(
    os.getenv("PENDING_STORIES_DIR", str(LORE_DIR / "historias" / "pendientes"))
)


def read_lore_file(relative_path: str) -> str:
    path = LORE_DIR / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_core_lore() -> str:
    resumen = read_lore_file("resumen-para-ia.md")
    reglas = read_lore_file("reglas-de-tono.md")
    return f"# Resumen de lore\n\n{resumen}\n\n# Reglas de tono\n\n{reglas}".strip()


CHARACTER_LORE_FILES = {
    "mimosuga": ("Mimosuga", "personajes/mimosuga.md"),
    "ululon": ("Ululon", "personajes/ululon.md"),
    "ululón": ("Ululon", "personajes/ululon.md"),
    "caparablanda": ("Caparablanda", "personajes/caparablanda.md"),
    "castora celestial": ("Castora Celestial", "personajes/castora-celestial.md"),
    "osito castori": ("Osito Castori", "personajes/osito-castori.md"),
    "donetito": ("Donetito", "personajes/donetito.md"),
}


def read_relevant_character_lore(text: str) -> str:
    lowered = text.lower()
    sections = []
    seen_paths = set()
    for trigger, (display_name, relative_path) in CHARACTER_LORE_FILES.items():
        if trigger not in lowered or relative_path in seen_paths:
            continue
        content = read_lore_file(relative_path)
        if content:
            sections.append(f"## {display_name}\n\n{content}")
            seen_paths.add(relative_path)

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
