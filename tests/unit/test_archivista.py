"""Test del nodo Archivista.

Se mockean DOS cosas: el modelo (Claude) y el cliente MCP
(``llamar_herramienta``). Este test no toca disco ni arranca ningun
proceso -- eso ya lo cubren los tests de mcp_obsidian/.
"""

from unittest.mock import patch

from grafo.estado import Estado, NotaPropuesta
from grafo.nodos.archivista import archivista


def test_archivista_llama_a_crear_nota_con_los_datos_correctos() -> None:
    propuesta_falsa = NotaPropuesta(titulo="Idea sobre Redis", tags=["redis", "infra"])

    with (
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
    ):
        estructurado = modelo_mock.return_value.with_structured_output.return_value
        estructurado.invoke.return_value = propuesta_falsa
        llamar_mock.return_value = ["00-inbox/idea-sobre-redis.md"]

        resultado = archivista(Estado(mensaje_usuario="me gusto la idea de usar Redis"))

    llamar_mock.assert_called_once_with(
        "crear_nota",
        titulo="Idea sobre Redis",
        tags=["redis", "infra"],
        contenido="me gusto la idea de usar Redis",
    )

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Idea sobre Redis" in respuesta
    assert "00-inbox/idea-sobre-redis.md" in respuesta
