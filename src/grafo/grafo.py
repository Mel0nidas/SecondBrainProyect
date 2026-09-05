"""Grafo de la Fase 2 (DISEÑO.md §2.2): Router + Archivista + Bibliotecario
+ respuesta directa, con corte por presupuesto.

Esto reemplaza el grafo de 2 nodos de la Fase 1 (que solo saludaba).
"""

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from grafo.estado import Estado, Intencion
from grafo.nodos.archivista import archivista
from grafo.nodos.bibliotecario import bibliotecario
from grafo.nodos.directo import directo
from grafo.nodos.presupuesto import resumen_parcial, verificar_presupuesto
from grafo.nodos.router import router


def _despues_de_verificar(estado: Estado) -> str:
    """Arista condicional: decide a donde ir despues de contar el paso."""
    if estado.presupuesto.excedido():
        return "resumen_parcial"
    if estado.intencion in (Intencion.CAPTURAR, Intencion.TAREA):
        return "archivista"
    if estado.intencion == Intencion.CONSULTAR:
        return "bibliotecario"
    return "directo"


def _despues_de_directo(estado: Estado) -> str:
    """Solo el comando de prueba "/test_loop" vuelve a pasar por el contador.

    Todo el resto de los mensajes termina el grafo en este punto.
    """
    if estado.mensaje_usuario.strip() == "/test_loop" and not estado.presupuesto.excedido():
        return "verificar_presupuesto"
    return END


def construir_grafo() -> CompiledStateGraph[Estado, None, Estado, Estado]:
    grafo = StateGraph(Estado)

    # Los "type: ignore" tapan una limitacion conocida de los overloads
    # de langgraph con mypy estricto -- no es un error real (ver Fase 1).
    grafo.add_node("router", router)  # type: ignore[call-overload]
    grafo.add_node("verificar_presupuesto", verificar_presupuesto)  # type: ignore[call-overload]
    grafo.add_node("archivista", archivista)  # type: ignore[call-overload]
    grafo.add_node("bibliotecario", bibliotecario)  # type: ignore[call-overload]
    grafo.add_node("directo", directo)  # type: ignore[call-overload]
    grafo.add_node("resumen_parcial", resumen_parcial)  # type: ignore[call-overload]

    grafo.set_entry_point("router")
    grafo.add_edge("router", "verificar_presupuesto")
    grafo.add_conditional_edges("verificar_presupuesto", _despues_de_verificar)
    grafo.add_conditional_edges("directo", _despues_de_directo)

    grafo.add_edge("archivista", END)
    grafo.add_edge("bibliotecario", END)
    grafo.add_edge("resumen_parcial", END)

    return grafo.compile()
