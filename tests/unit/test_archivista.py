"""Test del nodo Archivista: LLM mockeado, boveda redirigida a una carpeta
temporal (nunca escribe en la boveda_local real durante los tests).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from grafo import boveda_local
from grafo.estado import Estado, NotaPropuesta
from grafo.nodos.archivista import archivista


def test_archivista_crea_un_archivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(boveda_local, "RUTA_BOVEDA", tmp_path)

    propuesta_falsa = NotaPropuesta(titulo="Idea sobre Redis", tags=["redis", "infra"])

    with patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock:
        estructurado = modelo_mock.return_value.with_structured_output.return_value
        estructurado.invoke.return_value = propuesta_falsa

        resultado = archivista(Estado(mensaje_usuario="me gusto la idea de usar Redis"))

    archivos = list((tmp_path / "00-inbox").glob("*.md"))
    assert len(archivos) == 1

    contenido = archivos[0].read_text(encoding="utf-8")
    assert "Idea sobre Redis" in contenido
    assert "tags: [redis, infra]" in contenido

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Idea sobre Redis" in respuesta
