"""Test del nodo Archivista.

Se mockean TRES cosas: el modelo (Claude), el cliente MCP
(``llamar_herramienta``) y ``indexar_nota`` (Chroma + Voyage, Fase 4).
Este test no toca disco ni hace llamadas de red -- eso ya lo cubren los
tests de mcp_obsidian/ y rag/.
"""

from unittest.mock import patch

from grafo.estado import Estado, NotaPropuesta
from grafo.nodos.archivista import archivista


def test_archivista_llama_a_crear_nota_con_los_datos_correctos() -> None:
    propuesta_falsa = NotaPropuesta(titulo="Idea sobre Redis", tags=["redis", "infra"])

    with (
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota") as indexar_mock,
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
    indexar_mock.assert_called_once_with(
        ruta="00-inbox/idea-sobre-redis.md",
        titulo="Idea sobre Redis",
        tags=["redis", "infra"],
        contenido="me gusto la idea de usar Redis",
    )

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Idea sobre Redis" in respuesta
    assert "00-inbox/idea-sobre-redis.md" in respuesta
