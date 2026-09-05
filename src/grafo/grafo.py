"""Grafo minimo de 2 nodos (Fase 1: "hola mundo" de LangGraph).

Un "nodo" es simplemente una funcion Python que recibe el estado actual
y devuelve los campos que quiere actualizar. El grafo conecta nodos con
"edges" (flechas) que dicen que nodo sigue a cual. Este grafo no tiene
routing, herramientas ni memoria -- eso llega en la Fase 2 en adelante
(ver DISEÑO.md, PARTE 5).
"""

from langchain_anthropic import ChatAnthropic
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from grafo.estado import EstadoSaludo

# Verificar en la doc de Anthropic cual es el Sonnet vigente al construir
# (DISEÑO.md §4.2) -- no hardcodear esto en mas de un lugar del codigo.
MODELO = "claude-sonnet-4-6"


def preparar(estado: EstadoSaludo) -> dict[str, str]:
    """Nodo 1: por ahora solo deja pasar el mensaje.

    Esta como nodo separado para probar que el grafo puede tener mas de
    un paso encadenado, aunque en esta fase no transforma nada todavia.
    """
    return {"mensaje_usuario": estado.mensaje_usuario}


def preguntar_a_claude(estado: EstadoSaludo) -> dict[str, str]:
    """Nodo 2: le manda el mensaje a Claude y guarda la respuesta."""
    modelo = ChatAnthropic(model=MODELO)  # type: ignore[call-arg]
    respuesta = modelo.invoke(estado.mensaje_usuario)
    return {"respuesta": str(respuesta.content)}


def construir_grafo() -> CompiledStateGraph[EstadoSaludo, None, EstadoSaludo, EstadoSaludo]:
    """Arma y compila el grafo: preparar -> preguntar_a_claude -> fin.

    "Compilar" en LangGraph valida que el grafo este bien formado (todos
    los nodos conectados, sin callejones sin salida) y devuelve un objeto
    con un metodo ``.invoke()`` para correrlo.
    """
    grafo = StateGraph(EstadoSaludo)
    # Los "type: ignore" de abajo tapan una limitacion conocida de los
    # overloads de langgraph con mypy estricto -- no es un error real
    # en nuestro codigo.
    grafo.add_node("preparar", preparar)  # type: ignore[call-overload]
    grafo.add_node("preguntar_a_claude", preguntar_a_claude)  # type: ignore[call-overload]
    grafo.set_entry_point("preparar")
    grafo.add_edge("preparar", "preguntar_a_claude")
    grafo.add_edge("preguntar_a_claude", END)
    return grafo.compile()
