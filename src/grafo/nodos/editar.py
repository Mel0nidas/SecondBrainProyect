"""Nodo Editar (Fase 16): agrega algo a la última nota capturada.

*"agregale que el precio era 200"* justo después de guardar algo → se
suma esa línea al final de la nota, sin pasar por ``/corregir``.

La ruta de la última nota (``estado.ruta_nota_creada``) la deja el
Archivista, y el webhook la arrastra desde el checkpoint anterior a la
corrida nueva (por eso "la última que guardaste", no la de este mensaje).
"""

import re

from grafo.estado import Estado
from mcp_obsidian.cliente import llamar_herramienta
from rag.indexar import reindexar_nota

# Saca el "agregale que ..." del principio y deja solo lo que hay que
# agregar. Si no matchea nada, se agrega el mensaje entero.
_PREFIJO = re.compile(
    r"^\s*(agregale|agregá|agrega|sumale|sumá|suma|añadile|añadí|anotá|anota|y\s+también|también)"
    r"\b[:,]?\s*(que\s+)?",
    re.IGNORECASE,
)


def editar(estado: Estado) -> dict[str, object]:
    ruta = estado.ruta_nota_creada
    if not ruta:
        return {
            "respuesta_final": "No tengo una nota reciente para editar. Guardá algo primero."
        }

    agregado = _PREFIJO.sub("", estado.mensaje_usuario).strip() or estado.mensaje_usuario.strip()
    llamar_herramienta("agregar_a_nota", ruta_relativa=ruta, texto=agregado)
    reindexar_nota(ruta)

    return {"respuesta_final": f'Agregado a "{ruta}".', "ruta_nota_creada": ruta}
