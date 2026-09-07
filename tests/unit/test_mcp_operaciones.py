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


def test_mover_nota_reubica_el_archivo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    origen = operaciones.crear_nota(titulo="Llamar al banco", tags=[], contenido="mañana")

    nueva = operaciones.mover_nota(origen, operaciones.CARPETA_TAREAS)

    assert nueva == "20-tareas/llamar-al-banco.md"
    assert not (tmp_path / origen).exists()
    assert (tmp_path / nueva).read_text(encoding="utf-8").startswith("---")


def test_mover_nota_no_pisa_una_existente(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    origen = operaciones.crear_nota(titulo="Cosa", tags=[], contenido="version nueva")
    # Ya hay una nota con ese nombre en el destino, con otro contenido.
    destino = tmp_path / operaciones.CARPETA_TAREAS
    destino.mkdir()
    (destino / "cosa.md").write_text("version vieja", encoding="utf-8")

    resultado = operaciones.mover_nota(origen, operaciones.CARPETA_TAREAS)

    assert "no se movio" in resultado
    assert (tmp_path / origen).exists()  # el original sigue donde estaba
    assert (destino / "cosa.md").read_text(encoding="utf-8") == "version vieja"


def test_mover_nota_inexistente_no_explota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))

    resultado = operaciones.mover_nota("00-inbox/fantasma.md", operaciones.CARPETA_TAREAS)

    assert "No existe" in resultado


def test_agregar_a_lista_crea_y_no_repite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))

    abiertos = operaciones.agregar_a_lista("compras", ["pan", "leche"])
    assert abiertos == ["pan", "leche"]

    # "pan" ya esta -> no se duplica; "cafe" es nuevo.
    abiertos = operaciones.agregar_a_lista("compras", ["Pan", "cafe"])
    assert abiertos == ["pan", "leche", "cafe"]

    contenido = (tmp_path / "20-tareas" / "compras.md").read_text(encoding="utf-8")
    assert contenido.startswith("---")
    assert "# Compras" in contenido
    assert contenido.count("- [ ] pan") == 1


def test_marcar_en_lista_tacha_y_reporta_faltantes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    operaciones.agregar_a_lista("compras", ["pan integral", "leche"])

    marcados, faltantes = operaciones.marcar_en_lista("compras", ["pan", "servilletas"])

    assert marcados == ["pan integral"]  # match parcial, case-insensitive
    assert faltantes == ["servilletas"]
    assert operaciones.leer_lista("compras") == ["leche"]  # "pan integral" ya no esta abierto
    contenido = (tmp_path / "20-tareas" / "compras.md").read_text(encoding="utf-8")
    assert "- [x] pan integral" in contenido


def test_leer_y_listar_listas(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    assert operaciones.leer_lista("compras") == []
    assert operaciones.listar_listas() == []

    operaciones.agregar_a_lista("compras", ["pan"])
    operaciones.agregar_a_lista("farmacia", ["ibuprofeno"])

    assert operaciones.listar_listas() == ["compras", "farmacia"]
