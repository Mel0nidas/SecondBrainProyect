"""Test del nodo Bibliotecario.

La busqueda por palabras clave corre de verdad (no se mockea, es una
funcion simple y determinista). Solo se mockea la llamada a Claude que
redacta la respuesta final.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from grafo import boveda_local
from grafo.estado import Estado
from grafo.nodos.bibliotecario import bibliotecario


class _RespuestaFalsa:
    content = "Guardaste una idea sobre usar Redis como cache de corto plazo."


def test_bibliotecario_encuentra_una_nota_guardada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boveda_local, "RUTA_BOVEDA", tmp_path)
    boveda_local.crear_nota(
        titulo="Idea sobre Redis",
        tags=["redis"],
        contenido="Redis podria servir como cache de corto plazo.",
    )

    with patch("grafo.nodos.bibliotecario.ChatAnthropic") as modelo_mock:
        modelo_mock.return_value.invoke.return_value = _RespuestaFalsa()

        resultado = bibliotecario(Estado(mensaje_usuario="que guarde sobre Redis?"))

    assert resultado["snippets"]  # encontro al menos un fragmento

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Redis" in respuesta


def test_bibliotecario_sin_resultados_no_llama_al_modelo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(boveda_local, "RUTA_BOVEDA", tmp_path)

    resultado = bibliotecario(Estado(mensaje_usuario="pregunta sobre algo que nunca guarde"))

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "No encontre" in respuesta
