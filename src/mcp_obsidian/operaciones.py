"""Operaciones de archivo sobre la boveda de Obsidian (Fase 3).

Funciones puras de Python, sin nada de protocolo MCP -- eso permite
testearlas directo, sin levantar un servidor. ``servidor.py`` las
envuelve como "tools" de MCP.

Reemplaza a ``grafo/boveda_local.py`` (Fase 2): la diferencia es que
ahora la ruta no es una carpeta de prueba fija, sino la boveda real de
Obsidian, tomada de la variable de entorno ``RUTA_BOVEDA_OBSIDIAN``.
"""

import os
import re
from datetime import date, datetime
from pathlib import Path

CARPETA_INBOX = "00-inbox"
CARPETA_IMAGENES = "30-imagenes"


def ruta_boveda() -> Path:
    """Lee la ruta de la boveda desde el entorno en cada llamada.

    No se guarda en una constante de modulo a proposito: asi, si un
    test cambia la variable de entorno, esta funcion ve el cambio.
    """
    valor = os.environ.get("RUTA_BOVEDA_OBSIDIAN", "boveda_local")
    return Path(valor)


def _slug(texto: str) -> str:
    texto = texto.lower().strip()
    texto = re.sub(r"[^a-z0-9\s-]", "", texto)
    texto = re.sub(r"\s+", "-", texto)
    return texto[:60] or "nota"


def crear_nota(
    titulo: str,
    tags: list[str],
    contenido: str,
    carpeta: str = CARPETA_INBOX,
    origen: str = "cli",
) -> str:
    """Crea una nota markdown con frontmatter (DISEÑO.md §2.5).

    Por defecto cae en 00-inbox/, que es donde va todo lo capturado.
    ``carpeta`` existe para las notas de imagenes (Fase 7), que viven
    en 30-imagenes/ al lado de su foto.
    """
    destino = ruta_boveda() / carpeta
    destino.mkdir(parents=True, exist_ok=True)

    ruta_relativa = f"{carpeta}/{_slug(titulo)}.md"
    ruta_archivo = ruta_boveda() / ruta_relativa

    tags_yaml = ", ".join(tags)
    frontmatter = (
        "---\n"
        f"fecha: {date.today().isoformat()}\n"
        f"origen: {origen}\n"
        f"tags: [{tags_yaml}]\n"
        "estado: inbox\n"
        "---\n\n"
    )
    ruta_archivo.write_text(frontmatter + f"# {titulo}\n\n{contenido}\n", encoding="utf-8")
    return ruta_relativa


def guardar_imagen(datos: bytes, extension: str = "jpg") -> str:
    """Guarda una foto en 30-imagenes/ y devuelve su ruta relativa.

    El nombre se arma con la fecha y hora exacta, para que dos fotos
    mandadas el mismo dia no se pisen entre si.

    A diferencia del resto de las operaciones, esta la llama el webhook
    (``app/main.py``), no un agente: los bytes de una imagen no pasan
    por el protocolo MCP ni por el estado del grafo, solo su ruta.
    """
    destino = ruta_boveda() / CARPETA_IMAGENES
    destino.mkdir(parents=True, exist_ok=True)

    marca = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    ruta_relativa = f"{CARPETA_IMAGENES}/{marca}.{extension}"
    (ruta_boveda() / ruta_relativa).write_bytes(datos)
    return ruta_relativa


def leer_nota(ruta_relativa: str) -> str:
    """Lee una nota por su ruta relativa a la boveda (ej: "00-inbox/mi-nota.md")."""
    ruta_archivo = ruta_boveda() / ruta_relativa
    if not ruta_archivo.exists():
        return f"No existe una nota en {ruta_relativa}."
    return ruta_archivo.read_text(encoding="utf-8")


def agregar_a_nota(ruta_relativa: str, texto: str) -> str:
    """Agrega texto al final de una nota existente."""
    ruta_archivo = ruta_boveda() / ruta_relativa
    if not ruta_archivo.exists():
        return f"No existe una nota en {ruta_relativa}, no se agrego nada."
    with ruta_archivo.open("a", encoding="utf-8") as archivo:
        archivo.write(f"\n{texto}\n")
    return f"Agregado a {ruta_relativa}."


def listar_carpeta(carpeta: str = "") -> list[str]:
    """Lista las notas .md dentro de una carpeta de la boveda (recursivo)."""
    ruta_base = ruta_boveda() / carpeta
    if not ruta_base.exists():
        return []
    # .as_posix() fuerza "/" como separador siempre, sin importar el
    # sistema operativo -- si no, en Windows esto devuelve "\" y deja
    # de coincidir con las rutas armadas a mano (ej: en crear_nota).
    return sorted(p.relative_to(ruta_boveda()).as_posix() for p in ruta_base.rglob("*.md"))


def buscar_por_titulo(consulta: str, maximo: int = 3) -> list[str]:
    """Busqueda simple por palabras clave (placeholder del RAG real de Fase 4).

    Revisa titulo y contenido de cada nota. No es busqueda semantica
    todavia -- eso llega con Chroma en la Fase 4.
    """
    base = ruta_boveda()
    if not base.exists():
        return []

    palabras = [p for p in re.findall(r"\w+", consulta.lower()) if len(p) > 3]
    if not palabras:
        return []

    coincidencias: list[str] = []
    for archivo in sorted(base.rglob("*.md")):
        texto = archivo.read_text(encoding="utf-8").lower()
        if any(palabra in texto for palabra in palabras):
            coincidencias.append(archivo.read_text(encoding="utf-8"))
        if len(coincidencias) >= maximo:
            break

    return coincidencias
