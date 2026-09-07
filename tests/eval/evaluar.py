"""Set de evaluacion del Router (DISEÑO.md §6, Fase 9).

Corre cada mensaje etiquetado de ``mensajes.jsonl`` contra el Router
REAL -- es decir, pega a la API de Claude y cuesta unos centavos por
corrida. Mide la tasa de acierto de la intencion, que es la metrica de
la que depende todo el resto del grafo: si el Router clasifica mal, el
mensaje va al agente equivocado.

A diferencia de los tests de ``tests/unit`` (que mockean todo y no
gastan nada), esto NO se corre en cada push. Se dispara solo cuando un
PR toca los prompts o el nodo Router, o a mano
(ver ``.github/workflows/eval.yml`` y el README de esta carpeta).

Uso:
    uv run --env-file .env python -m tests.eval.evaluar
    uv run --env-file .env python -m tests.eval.evaluar --actualizar-baseline
    uv run --env-file .env python -m tests.eval.evaluar --umbral 0.80

Codigos de salida: 0 = OK, 1 = regresion (bajo el umbral), 2 = error de setup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from grafo.estado import Estado, Intencion
from grafo.nodos.router import router

AQUI = Path(__file__).parent
RUTA_SET = AQUI / "mensajes.jsonl"
RUTA_BASELINE = AQUI / "baseline.json"

# Cuanto puede bajar la tasa respecto del baseline antes de fallar. El
# Router usa un modelo: dos corridas del mismo set no dan exactamente lo
# mismo, y este margen absorbe ese ruido sin dejar pasar una regresion real.
MARGEN = 0.05


@dataclass
class Caso:
    mensaje: str
    intencion: Intencion
    fuente: str


@dataclass
class Fallo:
    mensaje: str
    esperado: Intencion
    predicho: Intencion


def cargar_set() -> list[Caso]:
    if not RUTA_SET.exists():
        print(f"[setup] no existe el set: {RUTA_SET}", file=sys.stderr)
        raise SystemExit(2)

    casos: list[Caso] = []
    for linea in RUTA_SET.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("//"):
            continue
        dato = json.loads(limpia)
        casos.append(
            Caso(
                mensaje=str(dato["mensaje"]),
                intencion=Intencion(dato["intencion"]),
                fuente=str(dato.get("fuente", "sintetico")),
            )
        )

    if not casos:
        print(f"[setup] el set esta vacio: {RUTA_SET}", file=sys.stderr)
        raise SystemExit(2)
    return casos


def correr(casos: list[Caso]) -> list[Fallo]:
    """Clasifica cada caso con el Router real. Devuelve solo los fallos."""
    fallos: list[Fallo] = []
    for n, caso in enumerate(casos, start=1):
        salida = router(Estado(mensaje_usuario=caso.mensaje))
        predicho = salida["intencion"]
        assert isinstance(predicho, Intencion)  # el Router siempre devuelve una Intencion

        ok = predicho == caso.intencion
        print(f"  [{n:2d}/{len(casos)}] {'ok' if ok else 'XX'}  "
              f"{caso.intencion.value:9s} {caso.mensaje[:64]}")
        if not ok:
            fallos.append(Fallo(mensaje=caso.mensaje, esperado=caso.intencion, predicho=predicho))
    return fallos


def reportar(casos: list[Caso], fallos: list[Fallo]) -> float:
    total = len(casos)
    aciertos = total - len(fallos)
    tasa = aciertos / total

    print(f"\nAciertos: {aciertos}/{total}  ->  {tasa:.1%}\n")

    fallos_por_esperado: dict[Intencion, list[Fallo]] = {}
    for f in fallos:
        fallos_por_esperado.setdefault(f.esperado, []).append(f)

    print("Por intencion esperada:")
    for intencion in Intencion:
        del_clase = [c for c in casos if c.intencion == intencion]
        if not del_clase:
            continue
        malos = fallos_por_esperado.get(intencion, [])
        bien = len(del_clase) - len(malos)
        confus = Counter(f.predicho.value for f in malos)
        extra = ""
        if confus:
            extra = "   -> " + ", ".join(f"{v}x {k}" for k, v in confus.most_common())
        print(f"  {intencion.value:9s} {bien}/{len(del_clase)}{extra}")

    if fallos:
        print("\nFallos:")
        for f in fallos:
            print(f'  {f.esperado.value:9s} -> {f.predicho.value:9s}  "{f.mensaje}"')

    return tasa


def _guardar_baseline(tasa: float, n: int) -> None:
    RUTA_BASELINE.write_text(
        json.dumps(
            {"tasa_acierto": round(tasa, 4), "fecha": date.today().isoformat(), "n": n},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluacion del Router (DISEÑO.md §6)")
    parser.add_argument(
        "--actualizar-baseline",
        action="store_true",
        help="Corre el set y guarda la tasa actual como nuevo baseline.",
    )
    parser.add_argument(
        "--umbral",
        type=float,
        default=None,
        help="Umbral absoluto fijo. Si no se pasa, se usa baseline - margen.",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[setup] falta ANTHROPIC_API_KEY. El eval pega a la API real de Claude.\n"
            "        local:  uv run --env-file .env python -m tests.eval.evaluar\n"
            "        en CI:  agregar ANTHROPIC_API_KEY en Settings -> Secrets -> Actions",
            file=sys.stderr,
        )
        return 2

    casos = cargar_set()
    reales = sum(1 for c in casos if c.fuente == "real")
    print("=== Evaluacion del Router ===")
    print(f"Set: {len(casos)} mensajes ({reales} reales, {len(casos) - reales} sinteticos)\n")

    fallos = correr(casos)
    tasa = reportar(casos, fallos)

    if args.actualizar_baseline:
        _guardar_baseline(tasa, len(casos))
        print(f"\nBaseline actualizado: {tasa:.1%} sobre {len(casos)} casos.")
        return 0

    if args.umbral is not None:
        umbral = args.umbral
        origen = "umbral fijo"
    elif RUTA_BASELINE.exists():
        base = json.loads(RUTA_BASELINE.read_text(encoding="utf-8"))
        umbral = float(base["tasa_acierto"]) - MARGEN
        origen = f"baseline {float(base['tasa_acierto']):.1%} - margen {MARGEN:.0%}"
    else:
        print(
            "\nNo hay baseline todavia. Fijalo con:\n"
            "  uv run --env-file .env python -m tests.eval.evaluar --actualizar-baseline"
        )
        return 0

    print(f"\nUmbral: {umbral:.1%}  ({origen})")
    if tasa + 1e-9 < umbral:
        print(f"RESULTADO: REGRESION  ({tasa:.1%} < {umbral:.1%})")
        return 1
    print(f"RESULTADO: OK  ({tasa:.1%} >= {umbral:.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
