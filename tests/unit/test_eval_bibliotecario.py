"""Tests de tests/eval/evaluar_bibliotecario.py.

El embeder real (Voyage AI) se reemplaza por uno falso basado en
solapamiento de palabras: dos textos que comparten palabras quedan con
vectores cercanos. No entiende significado -- alcanza para probar que el
cableado (chunkear -> indexar en Chroma -> buscar -> contar el top-k)
funciona. Que Voyage encuentre significados parecidos de verdad es lo
que mide el eval a mano, con la API real.

Ademas se valida que los archivos reales del set (corpus_bibliotecario/
y consultas_bibliotecario.jsonl) sean coherentes entre si.
"""

from __future__ import annotations

from tests.eval import evaluar_bibliotecario as ev

_VOCABULARIO = [
    "perro", "ladra", "fuerte", "jardin",
    "gato", "duerme", "dia", "sofa",
    "pajaro", "canta", "rama", "arbol",
]


def _fake_embeder(textos: list[str], tipo_entrada: str) -> list[list[float]]:
    """Vector = presencia (1/0) de cada palabra del vocabulario fijo.

    Con distancia L2, el texto que mas palabras comparte con la consulta
    queda mas cerca. Determinista y sin red.
    """
    vectores: list[list[float]] = []
    for texto in textos:
        palabras = set(texto.lower().split())
        vectores.append([1.0 if palabra in palabras else 0.0 for palabra in _VOCABULARIO])
    return vectores


def _corpus_juguete() -> list[ev.NotaCorpus]:
    return [
        ev.NotaCorpus("perro", "Perro", [], "el perro ladra fuerte en el jardin"),
        ev.NotaCorpus("gato", "Gato", [], "el gato duerme todo el dia en el sofa"),
        ev.NotaCorpus("pajaro", "Pajaro", [], "el pajaro canta en la rama del arbol"),
    ]


def test_recuperar_encuentra_la_nota_por_solapamiento() -> None:
    coleccion = ev.construir_indice(_corpus_juguete(), _fake_embeder)

    casos = [
        ev.Caso("el perro ladra", "perro", "sintetico"),
        ev.Caso("el gato duerme", "gato", "sintetico"),
    ]
    resultados = ev.recuperar(casos, coleccion, _fake_embeder, top_k=2)

    assert [r.acierto for r in resultados] == [True, True]
    assert resultados[0].recuperadas[0] == "perro"


def test_recuperar_marca_miss_cuando_la_nota_no_esta_en_el_top_k() -> None:
    coleccion = ev.construir_indice(_corpus_juguete(), _fake_embeder)

    # La consulta habla del gato pero se espera (mal a proposito) el pajaro.
    casos = [ev.Caso("el gato duerme en el sofa", "pajaro", "sintetico")]
    resultados = ev.recuperar(casos, coleccion, _fake_embeder, top_k=1)

    assert resultados[0].acierto is False
    assert resultados[0].recuperadas == ["gato"]


def test_recuperar_dedupe_de_chunks_de_la_misma_nota() -> None:
    # Una nota larga que se parte en varios chunks no debe contar como
    # varias notas distintas en el top-k.
    cuerpo = "## Uno\n\nel perro ladra fuerte\n\n## Dos\n\nel perro en el jardin"
    corpus = [ev.NotaCorpus("perro", "Perro", [], cuerpo)]
    coleccion = ev.construir_indice(corpus, _fake_embeder)

    resultados = ev.recuperar(
        [ev.Caso("el perro ladra en el jardin", "perro", "sintetico")],
        coleccion,
        _fake_embeder,
        top_k=3,
    )

    assert resultados[0].recuperadas == ["perro"]


def test_reportar_calcula_el_recall() -> None:
    resultados = [
        ev.Resultado(ev.Caso("q1", "a", "sintetico"), ["a", "b", "c"]),
        ev.Resultado(ev.Caso("q2", "x", "sintetico"), ["b", "c", "d"]),
        ev.Resultado(ev.Caso("q3", "b", "sintetico"), ["b"]),
        ev.Resultado(ev.Caso("q4", "z", "sintetico"), []),
    ]

    assert ev.reportar(resultados) == 0.5


def test_el_set_real_es_coherente_con_el_corpus() -> None:
    """consultas_bibliotecario.jsonl no referencia ninguna nota que no exista."""
    corpus = ev.cargar_corpus()
    casos = ev.cargar_consultas()

    assert len(corpus) >= 5
    assert len(casos) >= len(corpus)  # al menos una consulta por nota
    ev.validar_coherencia(corpus, casos)  # no debe levantar SystemExit
