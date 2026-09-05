"""Funciones chicas compartidas entre nodos."""

from pathlib import Path

RUTA_PROMPTS = Path(__file__).parent / "prompts"


def cargar_prompt(nombre: str) -> str:
    """Lee el archivo <nombre>.md de la carpeta prompts/ como texto plano."""
    return (RUTA_PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")
