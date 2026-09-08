"""Funciones chicas compartidas entre nodos."""

import os
from pathlib import Path

RUTA_PROMPTS = Path(__file__).parent / "prompts"

# Modelos por defecto (DISEÑO.md §4.2). El Router corre en el 100% de los
# mensajes -> el mas barato; el resto de los agentes razonan o escriben ->
# Sonnet. Verificar el modelo vigente en la doc de Anthropic al tocar esto.
MODELO_ROUTER_DEFAULT = "claude-haiku-4-5-20251001"
MODELO_AGENTES_DEFAULT = "claude-sonnet-5"


def cargar_prompt(nombre: str) -> str:
    """Lee el archivo <nombre>.md de la carpeta prompts/ como texto plano."""
    return (RUTA_PROMPTS / f"{nombre}.md").read_text(encoding="utf-8")


def modelo_router() -> str:
    """Modelo del nodo Router. Override con ``MODELO_ROUTER`` en el entorno."""
    return os.environ.get("MODELO_ROUTER", MODELO_ROUTER_DEFAULT)


def modelo_agentes() -> str:
    """Modelo de los agentes que razonan o escriben (Archivista,
    Bibliotecario, Recordatorio, Tareas, Digestor, visión). Override con
    ``MODELO_AGENTES`` en el entorno."""
    return os.environ.get("MODELO_AGENTES", MODELO_AGENTES_DEFAULT)
