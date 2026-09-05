"""Tests de mcp_obsidian/operaciones.py -- funciones puras, sin MCP."""

from pathlib import Path

import pytest

from mcp_obsidian import operaciones


def test_crear_nota_escribe_frontmatter_y_contenido(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))

    ruta_relativa = operaciones.crear_nota(
        titulo="Idea sobre Redis", tags=["redis", "infra"], contenido="Texto de prueba."
    )

    ruta_absoluta = tmp_path / ruta_relativa
    assert ruta_absoluta.exists()

    contenido = ruta_absoluta.read_text(encoding="utf-8")
    assert "tags: [redis, infra]" in contenido
    assert "# Idea sobre Redis" in contenido
    assert "Texto de prueba." in contenido


def test_leer_nota_devuelve_el_contenido(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    ruta_relativa = operaciones.crear_nota(titulo="Nota X", tags=[], contenido="hola")

    leido = operaciones.leer_nota(ruta_relativa)

    assert "hola" in leido


def test_leer_nota_inexistente_no_explota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))

    resultado = operaciones.leer_nota("00-inbox/no-existe.md")

    assert "No existe" in resultado


def test_agregar_a_nota_suma_texto_al_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    ruta_relativa = operaciones.crear_nota(titulo="Nota Y", tags=[], contenido="primera linea")

    operaciones.agregar_a_nota(ruta_relativa, "segunda linea")

    contenido = operaciones.leer_nota(ruta_relativa)
    assert "primera linea" in contenido
    assert "segunda linea" in contenido


def test_listar_carpeta_encuentra_las_notas_creadas(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    operaciones.crear_nota(titulo="Una", tags=[], contenido="a")
    operaciones.crear_nota(titulo="Otra", tags=[], contenido="b")

    notas = operaciones.listar_carpeta("00-inbox")

    assert len(notas) == 2


def test_buscar_por_titulo_encuentra_coincidencias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    operaciones.crear_nota(
        titulo="Idea sobre Redis", tags=[], contenido="Redis sirve como cache."
    )

    encontradas = operaciones.buscar_por_titulo("que dije sobre Redis?")

    assert len(encontradas) == 1
    assert "Redis" in encontradas[0]


def test_buscar_por_titulo_sin_boveda_no_explota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path / "no-existe-todavia"))

    assert operaciones.buscar_por_titulo("cualquier cosa") == []
