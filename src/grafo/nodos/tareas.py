"""Nodo Tareas (Fase 11): listas de pendientes con checkboxes.

La intencion ``tarea`` deja de crear una nota por tarea y pasa a manejar
LISTAS: "compra pan la proxima vez que vayas al super" suma "- [ ] pan" a
``20-tareas/compras.md``. Cada lista es una nota markdown; el modelo
decide a que lista va cada cosa y si el usuario quiere agregar, marcar
hecho, o solo ver la lista.

Cuando una operacion modifica la lista, se la reindexa en el acto (igual
que el Archivista con las capturas), para que el Bibliotecario la
encuentre sin esperar al loop de sincronizacion de ~5 min (Fase 12).
"""

import logging

from langchain_anthropic import ChatAnthropic

from costos import registro as costos
from grafo.estado import Estado, OperacionLista
from grafo.utilidades import cargar_prompt, modelo_agentes
from mcp_obsidian import operaciones
from rag.indexar import reindexar_nota

logger = logging.getLogger(__name__)

MODELO_TAREAS = modelo_agentes()


def _reindexar_lista(nombre: str) -> None:
    """Reindexa la lista recien tocada. Si falla (tipico: rate limit de
    Voyage) se loguea y se sigue -- el loop de sincronizacion la levanta
    despues igual, asi que no vale romper la respuesta al usuario por esto."""
    try:
        reindexar_nota(operaciones.ruta_relativa_lista(nombre))
    except Exception as error:  # noqa: BLE001 -- el reindex nunca debe tumbar la respuesta
        logger.warning("Reindex de la lista %s pospuesto: %s", nombre, error)


def _formato_lista(nombre: str, items: list[str]) -> str:
    if not items:
        return f'La lista "{nombre}" esta vacia.'
    cuerpo = "\n".join(f"• {i}" for i in items)
    return f"Lista {nombre}:\n{cuerpo}"


def tareas(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_TAREAS)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(OperacionLista, include_raw=True)

    prompt = cargar_prompt("tareas")
    op = costos.extraer(
        modelo_estructurado.invoke(f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}"),
        MODELO_TAREAS,
        "tareas",
    )
    assert isinstance(op, OperacionLista)

    lista = op.lista.strip() or "pendientes"
    items = [i.strip() for i in op.items if i.strip()]

    if op.operacion == "completar":
        marcados, faltantes = operaciones.marcar_en_lista(lista, items)
        if marcados:
            _reindexar_lista(lista)
        lineas: list[str] = []
        if marcados:
            lineas.append("Marque: " + ", ".join(marcados) + ".")
        if faltantes:
            lineas.append("No estaban abiertas en la lista: " + ", ".join(faltantes) + ".")
        lineas.append(_formato_lista(lista, operaciones.leer_lista(lista)))
        return {"respuesta_final": "\n".join(lineas)}

    if op.operacion == "agregar" and items:
        antes = operaciones.leer_lista(lista)
        abiertos = operaciones.agregar_a_lista(lista, items)
        if set(abiertos) != set(antes):  # algo se agrego de verdad (no todo duplicado)
            _reindexar_lista(lista)
        return {
            "respuesta_final": (
                f"Agregue {', '.join(items)} a {lista}.\n" + _formato_lista(lista, abiertos)
            )
        }

    # "mostrar" -- o un "agregar" sin items, que tratamos como mostrar.
    return {"respuesta_final": _formato_lista(lista, operaciones.leer_lista(lista))}
