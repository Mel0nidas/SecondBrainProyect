"""Test del nodo Bibliotecario.

Se mockean el modelo (Claude) y ``buscar_con_fuente`` (Chroma + Voyage)
-- este test no toca disco ni hace llamadas de red.
"""

from unittest.mock import patch

from grafo.estado import Estado
from grafo.nodos.bibliotecario import bibliotecario
from rag.indexar import Fragmento


class _RespuestaFalsa:
    content = "Guardaste una idea sobre usar Redis como cache, segun [[Idea Redis]]."
    usage_metadata = {"input_tokens": 120, "output_tokens": 20}


def test_bibliotecario_responde_y_cita_las_fuentes() -> None:
    with (
        patch("grafo.nodos.bibliotecario.buscar_con_fuente") as buscar_mock,
        patch("grafo.nodos.bibliotecario.ChatAnthropic") as modelo_mock,
    ):
        buscar_mock.return_value = [
            Fragmento(texto="Redis podria servir como cache.", ruta="10-notas/idea-redis.md",
                      titulo="Idea Redis"),
            Fragmento(texto="Otra mencion de Redis.", ruta="10-notas/idea-redis.md",
                      titulo="Idea Redis"),
        ]
        modelo_mock.return_value.invoke.return_value = _RespuestaFalsa()

        resultado = bibliotecario(Estado(mensaje_usuario="que guarde sobre Redis?"))

    buscar_mock.assert_called_once_with("que guarde sobre Redis?")
    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Redis" in respuesta
    # una sola fuente aunque haya dos fragmentos de la misma nota
    assert respuesta.endswith("Fuentes: [[Idea Redis]]")
    assert resultado["snippets"] == ["Redis podria servir como cache.", "Otra mencion de Redis."]


def test_bibliotecario_sin_resultados_no_llama_al_modelo() -> None:
    with (
        patch("grafo.nodos.bibliotecario.buscar_con_fuente") as buscar_mock,
        patch("grafo.nodos.bibliotecario.ChatAnthropic") as modelo_mock,
    ):
        buscar_mock.return_value = []

        resultado = bibliotecario(Estado(mensaje_usuario="algo que nunca guarde"))

    modelo_mock.assert_not_called()
    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "No encontre" in respuesta
