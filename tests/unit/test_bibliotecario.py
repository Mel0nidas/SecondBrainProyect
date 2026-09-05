"""Test del nodo Bibliotecario.

Se mockean el modelo (Claude) y ``buscar_semantico`` (Chroma + Voyage)
-- este test no toca disco ni hace llamadas de red.
"""

from unittest.mock import patch

from grafo.estado import Estado
from grafo.nodos.bibliotecario import bibliotecario


class _RespuestaFalsa:
    content = "Guardaste una idea sobre usar Redis como cache de corto plazo."


def test_bibliotecario_responde_con_lo_que_encuentra() -> None:
    with (
        patch("grafo.nodos.bibliotecario.buscar_semantico") as buscar_mock,
        patch("grafo.nodos.bibliotecario.ChatAnthropic") as modelo_mock,
    ):
        buscar_mock.return_value = ["Redis podria servir como cache."]
        modelo_mock.return_value.invoke.return_value = _RespuestaFalsa()

        resultado = bibliotecario(Estado(mensaje_usuario="que guarde sobre Redis?"))

    buscar_mock.assert_called_once_with("que guarde sobre Redis?")

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Redis" in respuesta


def test_bibliotecario_sin_resultados_no_llama_al_modelo() -> None:
    with (
        patch("grafo.nodos.bibliotecario.buscar_semantico") as buscar_mock,
        patch("grafo.nodos.bibliotecario.ChatAnthropic") as modelo_mock,
    ):
        buscar_mock.return_value = []

        resultado = bibliotecario(Estado(mensaje_usuario="algo que nunca guarde"))

    modelo_mock.assert_not_called()

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "No encontre" in respuesta
