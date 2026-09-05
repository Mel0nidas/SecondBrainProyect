"""Tests de rag/indexar.py.

``_embeber`` se reemplaza (monkeypatch) por una version falsa en TODOS
estos tests: asi no se gasta ni una sola llamada real a Voyage AI al
correr `pytest`, y los tests corren sin necesitar internet ni API key.

La version falsa no entiende significado de verdad -- solo hace que el
mismo texto siempre de el mismo vector, y textos identicos den vectores
identicos. Eso alcanza para probar que el "cableado" (cortar -> guardar
-> buscar -> devolver) funciona. Que Voyage encuentre significados
parecidos de verdad es algo que se prueba a mano, con la cuenta real,
no en este archivo.
"""

from pathlib import Path

import pytest

from rag import indexar


def _fake_embed_por_largo(textos: list[str], tipo_entrada: str) -> list[list[float]]:
    """Embebedor falso: el vector es simplemente [longitud del texto].

    Determinista y sin red. No hace falta que tenga sentido semantico
    para probar que Chroma guarda y devuelve lo que corresponde.
    """
    return [[float(len(texto))] for texto in textos]


@pytest.fixture(autouse=True)
def _boveda_e_indice_temporales(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path / "boveda"))
    monkeypatch.setenv("RUTA_INDICE_CHROMA", str(tmp_path / "chroma"))
    monkeypatch.setattr(indexar, "_embeber", _fake_embed_por_largo)


def test_dividir_en_chunks_no_corta_texto_corto() -> None:
    texto = "## Titulo\n\nUn parrafo cortito."

    chunks = indexar.dividir_en_chunks(texto, tokens_max=500)

    assert len(chunks) == 1
    assert "Un parrafo cortito." in chunks[0]


def test_dividir_en_chunks_corta_por_encabezados() -> None:
    texto = "## Primero\n\nTexto A.\n\n## Segundo\n\nTexto B."

    chunks = indexar.dividir_en_chunks(texto, tokens_max=500)

    assert len(chunks) == 2
    assert "Texto A." in chunks[0]
    assert "Texto B." in chunks[1]


def test_dividir_en_chunks_corta_seccion_larga_por_parrafos() -> None:
    parrafo_corto = "palabra " * 15  # ~120 caracteres
    parrafos = "\n\n".join([parrafo_corto] * 6)  # ~720 caracteres, 6 parrafos separables
    texto = f"## Seccion larga\n\n{parrafos}"

    chunks = indexar.dividir_en_chunks(texto, tokens_max=50)  # limite ~200 caracteres

    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)  # con margen del encabezado


def test_indexar_nota_devuelve_cantidad_de_chunks() -> None:
    cantidad = indexar.indexar_nota(
        ruta="00-inbox/idea.md",
        titulo="Idea",
        tags=["redis"],
        contenido="## Seccion unica\n\nUn poco de contenido.",
    )

    assert cantidad == 1


def test_indexar_y_buscar_semantico_encuentra_el_chunk() -> None:
    indexar.indexar_nota(
        ruta="00-inbox/presupuesto.md",
        titulo="Presupuesto",
        tags=["finanzas"],
        contenido="## Gastos\n\nEste mes el presupuesto goes ok.",
    )

    encontrados = indexar.buscar_semantico("Este mes el presupuesto goes ok.", top_k=1)

    assert len(encontrados) == 1
    assert "presupuesto" in encontrados[0]


def test_buscar_semantico_sin_nada_indexado_no_explota() -> None:
    assert indexar.buscar_semantico("cualquier cosa") == []


def test_reindexar_nota_borra_los_chunks_viejos() -> None:
    indexar.indexar_nota(
        ruta="00-inbox/nota.md", titulo="Nota", tags=[], contenido="## A\n\nversion vieja"
    )
    indexar.indexar_nota(
        ruta="00-inbox/nota.md", titulo="Nota", tags=[], contenido="## A\n\nversion nueva"
    )

    # Si quedaran fantasmas de la version vieja, esto traeria 2.
    encontrados = indexar.buscar_semantico("version nueva", top_k=5)

    assert sum("version" in e for e in encontrados) == 1


def test_reindexar_todo_recorre_la_boveda(monkeypatch: pytest.MonkeyPatch) -> None:
    from mcp_obsidian import operaciones

    operaciones.crear_nota(titulo="Nota Uno", tags=["a"], contenido="Contenido uno.")
    operaciones.crear_nota(titulo="Nota Dos", tags=["b"], contenido="Contenido dos.")

    total = indexar.reindexar_todo()

    assert total == 2
