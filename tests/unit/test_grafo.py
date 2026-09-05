"""Tests del grafo de Fase 1.

El modelo (ChatAnthropic) se reemplaza por un "mock" -- un objeto falso
que simula la respuesta -- para no depender de una API key real ni
gastar tokens cada vez que corre el CI. Esto valida que el grafo esta
bien armado (los nodos se conectan y el estado fluye), no que Claude
responda bien (eso se prueba a mano, corriendo `python -m grafo`).
"""

from unittest.mock import MagicMock, patch

from grafo.estado import EstadoSaludo
from grafo.grafo import construir_grafo


def test_grafo_devuelve_la_respuesta_del_modelo() -> None:
    respuesta_falsa = MagicMock()
    respuesta_falsa.content = "hola, soy un grafo de LangGraph"

    with patch("grafo.grafo.ChatAnthropic") as modelo_mock:
        modelo_mock.return_value.invoke.return_value = respuesta_falsa

        grafo = construir_grafo()
        resultado = grafo.invoke(EstadoSaludo(mensaje_usuario="hola"))

    assert resultado["respuesta"] == "hola, soy un grafo de LangGraph"
