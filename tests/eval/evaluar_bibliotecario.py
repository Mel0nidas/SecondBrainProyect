"""Evaluacion secundaria: recall@3 del Bibliotecario (DISEÑO.md §6, Fase 9).

El eval del Router (``evaluar.py``) mide *a donde* manda cada mensaje.
Esto mide lo otro: cuando el mensaje va al Bibliotecario, ¿la nota que
responde la pregunta aparece entre las 3 primeras que trae la busqueda
semantica?

Como funciona:

1. ``corpus_bibliotecario/`` tiene un puñado de notas fijas, cada una
   sobre un tema distinto.
2. ``consultas_bibliotecario.jsonl`` tiene preguntas etiquetadas con la
   nota que deberia responderlas. Cada pregunta usa palabras DISTINTAS a
   las de su nota -- si bastara un grep, no estariamos midiendo nada.
3. Se arma un indice Chroma en memoria con el corpus, se corre cada
   consulta y se cuenta en cuantas la nota esperada quedo en el top 3.

NO llama al LLM: no evalua como redacta el Bibliotecario, solo si
*recupera* bien (que es la metrica secundaria que pide el DISEÑO). Si
pega a Voyage AI para los embeddings, pero en 2 requests por corrida
(todo el corpus junto, todas las consultas juntas), muy por debajo del
limite de 3/min de la cuenta sin tarjeta.

Uso:
    uv run --env-file .env python -m tests.eval.evaluar_bibliotecario
    uv run --env-file .env python -m tests.eval.evaluar_bibliotecario --actualizar-baseline
    uv run --env-file .env python -m tests.eval.evaluar_bibliotecario --umbral 0.80

Codigos de salida: 0 = OK, 1 = regresion (bajo el umbral), 2 = error de setup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import chromadb

from rag.indexar import _embeber, _parsear_nota, dividir_en_chunks

AQUI = Path(__file__).parent
DIR_CORPUS = AQUI / "corpus_bibliotecario"
RUTA_CONSULTAS = AQUI / "consultas_bibliotecario.jsonl"
RUTA_BASELINE = AQUI / "baseline_bibliotecario.json"

TOP_K = 3

# Cuanto puede bajar el recall respecto del baseline antes de fallar. Los
# embeddings de Voyage son deterministas, asi que dos corridas del mismo
# set dan el mismo numero; este margen cubre que Voyage actualice el
# modelo o que se edite una nota del corpus. Con ~14 consultas, una que
# se de vuelta son ~7 puntos: el margen deja pasar eso sin falsa alarma.
MARGEN = 0.10

# Funcion que convierte una lista de textos en vectores. La real es
# ``rag.indexar._embeber`` (pega a Voyage); los tests inyectan una falsa.
Embeder = Callable[[list[str], Literal["document", "query"]], list[list[float]]]


@dataclass
class NotaCorpus:
    ruta: str  # nombre de archivo sin .md, tal como se referencia en el set
    titulo: str
    tags: list[str]
    cuerpo: str


@dataclass
class Caso:
    consulta: str
    nota_esperada: str
    fuente: str


@dataclass
class Resultado:
    caso: Caso
    recuperadas: list[str]  # rutas del top-k, en orden

    @property
    def acierto(self) -> bool:
        return self.caso.nota_esperada in self.recuperadas

    @property
    def acierto_top1(self) -> bool:
        return bool(self.recuperadas) and self.recuperadas[0] == self.caso.nota_esperada


def cargar_corpus() -> list[NotaCorpus]:
    if not DIR_CORPUS.is_dir():
        print(f"[setup] no existe el corpus: {DIR_CORPUS}", file=sys.stderr)
        raise SystemExit(2)

    notas: list[NotaCorpus] = []
    for archivo in sorted(DIR_CORPUS.glob("*.md")):
        titulo, tags, cuerpo = _parsear_nota(archivo.read_text(encoding="utf-8"))
        notas.append(NotaCorpus(ruta=archivo.stem, titulo=titulo, tags=tags, cuerpo=cuerpo))

    if not notas:
        print(f"[setup] el corpus esta vacio: {DIR_CORPUS}", file=sys.stderr)
        raise SystemExit(2)
    return notas


def cargar_consultas() -> list[Caso]:
    if not RUTA_CONSULTAS.exists():
        print(f"[setup] no existe el set de consultas: {RUTA_CONSULTAS}", file=sys.stderr)
        raise SystemExit(2)

    casos: list[Caso] = []
    for linea in RUTA_CONSULTAS.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("//"):
            continue
        dato = json.loads(limpia)
        casos.append(
            Caso(
                consulta=str(dato["consulta"]),
                nota_esperada=str(dato["nota_esperada"]),
                fuente=str(dato.get("fuente", "sintetico")),
            )
        )

    if not casos:
        print(f"[setup] el set de consultas esta vacio: {RUTA_CONSULTAS}", file=sys.stderr)
        raise SystemExit(2)
    return casos


def validar_coherencia(corpus: list[NotaCorpus], casos: list[Caso]) -> None:
    """Cada ``nota_esperada`` del set tiene que existir en el corpus."""
    rutas = {n.ruta for n in corpus}
    huerfanas = sorted({c.nota_esperada for c in casos} - rutas)
    if huerfanas:
        print(
            "[setup] estas notas esperadas no estan en el corpus: " + ", ".join(huerfanas),
            file=sys.stderr,
        )
        raise SystemExit(2)


def construir_indice(corpus: list[NotaCorpus], embeder: Embeder) -> chromadb.Collection:
    """Arma una coleccion Chroma en memoria con el corpus, chunk por chunk.

    Embebe TODOS los chunks en una sola llamada -- por el rate limit de
    Voyage y porque no hay razon para hacer una request por nota.
    """
    textos: list[str] = []
    metadatas: list[dict[str, str]] = []
    for nota in corpus:
        for chunk in dividir_en_chunks(nota.cuerpo):
            textos.append(chunk)
            metadatas.append({"ruta": nota.ruta, "titulo": nota.titulo})

    if not textos:
        print("[setup] el corpus no produjo ningun chunk indexable", file=sys.stderr)
        raise SystemExit(2)

    vectores = embeder(textos, "document")
    # Nombre unico: el cliente en memoria de Chroma es compartido dentro del
    # proceso, y dos corridas seguidas (p. ej. en los tests) chocarian con
    # "collection already exists" si reusaran el mismo nombre.
    cliente = chromadb.EphemeralClient()
    coleccion = cliente.create_collection(f"eval_bibliotecario_{uuid.uuid4().hex}")
    coleccion.add(
        ids=[str(i) for i in range(len(textos))],
        embeddings=vectores,  # type: ignore[arg-type]
        documents=textos,
        metadatas=metadatas,  # type: ignore[arg-type]
    )
    return coleccion


def recuperar(
    casos: list[Caso], coleccion: chromadb.Collection, embeder: Embeder, top_k: int = TOP_K
) -> list[Resultado]:
    """Para cada consulta, devuelve las rutas de las ``top_k`` NOTAS mas cercanas.

    Chroma devuelve chunks, no notas, y una nota larga aporta varios. Se
    piden de mas (``top_k * 5``) y despues se deduplica por nota, para que
    "top-3" signifique 3 notas distintas y no 3 chunks que podrian ser
    todos de la misma.
    """
    vectores = embeder([c.consulta for c in casos], "query")
    chunks_a_pedir = min(top_k * 5, coleccion.count())
    resultados: list[Resultado] = []
    for caso, vector in zip(casos, vectores, strict=True):
        respuesta = coleccion.query(
            query_embeddings=[vector],  # type: ignore[arg-type]
            n_results=chunks_a_pedir,
            include=["metadatas"],
        )
        metadatas = (respuesta.get("metadatas") or [[]])[0]
        rutas: list[str] = []
        for meta in metadatas:
            ruta = str(meta.get("ruta", ""))
            if ruta and ruta not in rutas:
                rutas.append(ruta)
            if len(rutas) == top_k:
                break
        resultados.append(Resultado(caso=caso, recuperadas=rutas))
    return resultados


def reportar(resultados: list[Resultado]) -> float:
    """Imprime el detalle y devuelve el recall@TOP_K (la metrica que corta).

    Tambien muestra el recall@1 como señal extra: es mas sensible a que la
    recuperacion empeore, pero mas ruidoso, asi que no se usa de umbral.
    """
    total = len(resultados)
    aciertos = sum(1 for r in resultados if r.acierto)
    aciertos_top1 = sum(1 for r in resultados if r.acierto_top1)
    recall = aciertos / total

    for n, r in enumerate(resultados, start=1):
        if r.acierto_top1:
            marca = "ok "
        elif r.acierto:
            marca = "~3 "  # estaba en el top-3 pero no primera
        else:
            marca = "XX "
        print(f"  [{n:2d}/{total}] {marca} esperaba {r.caso.nota_esperada:24s}")
        print(f"           consulta: \"{r.caso.consulta}\"")
        if not r.acierto:
            print(f"           trajo:    {', '.join(r.recuperadas) or '(nada)'}")

    print(f"\nrecall@1:  {aciertos_top1}/{total}  ->  {aciertos_top1 / total:.1%}   (informativo)")
    print(f"recall@{TOP_K}:  {aciertos}/{total}  ->  {recall:.1%}   (umbral)")
    return recall


def _guardar_baseline(resultados: list[Resultado]) -> None:
    n = len(resultados)
    recall3 = sum(1 for r in resultados if r.acierto) / n
    recall1 = sum(1 for r in resultados if r.acierto_top1) / n
    RUTA_BASELINE.write_text(
        json.dumps(
            {
                "recall_at_3": round(recall3, 4),
                "recall_at_1": round(recall1, 4),  # informativo, no corta
                "fecha": date.today().isoformat(),
                "n": n,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluacion secundaria del Bibliotecario: recall@3 (DISEÑO.md §6)"
    )
    parser.add_argument(
        "--actualizar-baseline",
        action="store_true",
        help="Corre el set y guarda el recall actual como nuevo baseline.",
    )
    parser.add_argument(
        "--umbral",
        type=float,
        default=None,
        help="Umbral absoluto fijo. Si no se pasa, se usa baseline - margen.",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("VOYAGE_API_KEY"):
        print(
            "[setup] falta VOYAGE_API_KEY. El eval pega a Voyage AI para los embeddings.\n"
            "        local:  uv run --env-file .env python -m tests.eval.evaluar_bibliotecario\n"
            "        en CI:  agregar VOYAGE_API_KEY en Settings -> Secrets -> Actions",
            file=sys.stderr,
        )
        return 2

    corpus = cargar_corpus()
    casos = cargar_consultas()
    validar_coherencia(corpus, casos)

    reales = sum(1 for c in casos if c.fuente == "real")
    print("=== Evaluacion del Bibliotecario (recall@3) ===")
    print(f"Corpus: {len(corpus)} notas")
    print(f"Set: {len(casos)} consultas ({reales} reales, {len(casos) - reales} sinteticas)\n")

    coleccion = construir_indice(corpus, _embeber)
    resultados = recuperar(casos, coleccion, _embeber)
    recall = reportar(resultados)

    if args.actualizar_baseline:
        _guardar_baseline(resultados)
        print(f"\nBaseline actualizado: recall@{TOP_K} {recall:.1%} sobre {len(casos)} consultas.")
        return 0

    if args.umbral is not None:
        umbral = args.umbral
        origen = "umbral fijo"
    elif RUTA_BASELINE.exists():
        base = json.loads(RUTA_BASELINE.read_text(encoding="utf-8"))
        umbral = float(base["recall_at_3"]) - MARGEN
        origen = f"baseline {float(base['recall_at_3']):.1%} - margen {MARGEN:.0%}"
    else:
        print(
            "\nNo hay baseline todavia. Fijalo con:\n"
            "  uv run --env-file .env python -m tests.eval.evaluar_bibliotecario"
            " --actualizar-baseline"
        )
        return 0

    print(f"\nUmbral: {umbral:.1%}  ({origen})")
    if recall + 1e-9 < umbral:
        print(f"RESULTADO: REGRESION  ({recall:.1%} < {umbral:.1%})")
        return 1
    print(f"RESULTADO: OK  ({recall:.1%} >= {umbral:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
