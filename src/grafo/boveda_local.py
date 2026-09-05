"""Herramientas "falsas" del Archivista y el Bibliotecario (Fase 2).

Estas funciones leen y escriben en una carpeta local cualquiera, no en
una boveda de Obsidian real. Existen para poder probar el flujo
completo (capturar -> guardar, preguntar -> encontrar) sin depender
todavia del servidor MCP de Obsidian, que se construye en la Fase 3.

Cuando llegue la Fase 3, estas funciones se reemplazan por llamadas al
MCP server (``crear_nota``, ``buscar_por_titulo``, etc.), pero se
mantienen los mismos nombres para que los nodos que las usan
(``archivista.py``, ``bibliotecario.py``) casi no tengan que cambiar.
"""

import re
from datetime import date
from pathlib import Path

RUTA_BOVEDA = Path("boveda_local")
CARPETA_INBOX = "00-inbox"


def _slug(texto: str) -> str:
    """Convierte un titulo en un nombre de archivo simple y seguro.

    Por ejemplo, "Idea: usar Redis!" se convierte en "idea-usar-redis".
    """
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9\s-]", "", texto)
    texto = re.sub(r"\s+", "-", texto)
    return texto[:60] or "nota"


def crear_nota(
    titulo: str, tags: list[str], contenido: str, ruta_boveda: Path | None = None
) -> Path:
    """Crea una nota markdown en 00-inbox/, con frontmatter (DISEÑO.md §2.5)."""
    ruta_base = ruta_boveda if ruta_boveda is not None else RUTA_BOVEDA
    carpeta = ruta_base / CARPETA_INBOX
    carpeta.mkdir(parents=True, exist_ok=True)

    nombre_archivo = f"{_slug(titulo)}.md"
    ruta_archivo = carpeta / nombre_archivo

    tags_yaml = ", ".join(tags)
    frontmatter = (
        "---\n"
        f"fecha: {date.today().isoformat()}\n"
        "origen: cli\n"
        f"tags: [{tags_yaml}]\n"
        "estado: inbox\n"
        "---\n\n"
    )
    ruta_archivo.write_text(frontmatter + f"# {titulo}\n\n{contenido}\n", encoding="utf-8")
    return ruta_archivo


def buscar_notas(consulta: str, ruta_boveda: Path | None = None, maximo: int = 3) -> list[str]:
    """Busqueda simple por palabras clave (placeholder del RAG de Fase 4).

    No es busqueda semantica todavia -- solo revisa si alguna palabra
    de la consulta aparece en el contenido de cada nota. Devuelve el
    contenido completo de las notas que matchean, hasta ``maximo``.
    """
    ruta_base = ruta_boveda if ruta_boveda is not None else RUTA_BOVEDA
    if not ruta_base.exists():
        return []

    palabras = [p for p in re.findall(r"\w+", consulta.lower()) if len(p) > 3]
    if not palabras:
        return []

    coincidencias: list[str] = []
    for archivo in sorted(ruta_base.rglob("*.md")):
        texto = archivo.read_text(encoding="utf-8").lower()
        if any(palabra in texto for palabra in palabras):
            coincidencias.append(archivo.read_text(encoding="utf-8"))
        if len(coincidencias) >= maximo:
            break

    return coincidencias
