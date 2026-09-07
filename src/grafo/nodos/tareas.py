"""Nodo Tareas (Fase 11): listas de pendientes con checkboxes.

La intencion ``tarea`` deja de crear una nota por tarea y pasa a manejar
LISTAS: "compra pan la proxima vez que vayas al super" suma "- [ ] pan" a
``20-tareas/compras.md``. Cada lista es una nota markdown; el modelo
decide a que lista va cada cosa y si el usuario quiere agregar, marcar
hecho, o solo ver la lista.
"""

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado, OperacionLista
from grafo.utilidades import cargar_prompt
from mcp_obsidian import operaciones

MODELO_TAREAS = "claude-sonnet-4-6"


def _formato_lista(nombre: str, items: list[str]) -> str:
    if not items:
        return f'La lista "{nombre}" esta vacia.'
    cuerpo = "\n".join(f"• {i}" for i in items)
    return f"Lista {nombre}:\n{cuerpo}"


def tareas(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_TAREAS)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(OperacionLista)

    prompt = cargar_prompt("tareas")
    op = modelo_estructurado.invoke(f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}")
    assert isinstance(op, OperacionLista)

    lista = op.lista.strip() or "pendientes"
    items = [i.strip() for i in op.items if i.strip()]

    if op.operacion == "completar":
        marcados, faltantes = operaciones.marcar_en_lista(lista, items)
        lineas: list[str] = []
        if marcados:
            lineas.append("Marque: " + ", ".join(marcados) + ".")
        if faltantes:
            lineas.append("No estaban abiertas en la lista: " + ", ".join(faltantes) + ".")
        lineas.append(_formato_lista(lista, operaciones.leer_lista(lista)))
        return {"respuesta_final": "\n".join(lineas)}

    if op.operacion == "agregar" and items:
        abiertos = operaciones.agregar_a_lista(lista, items)
        return {
            "respuesta_final": (
                f"Agregue {', '.join(items)} a {lista}.\n" + _formato_lista(lista, abiertos)
            )
        }

    # "mostrar" -- o un "agregar" sin items, que tratamos como mostrar.
    return {"respuesta_final": _formato_lista(lista, operaciones.leer_lista(lista))}
