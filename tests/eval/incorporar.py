"""Incorpora las correcciones de ``/corregir`` al set de evaluacion.

El bot no puede escribir ``tests/eval/mensajes.jsonl`` (el contenedor
tiene ``src/`` pero no ``tests/``). Cada ``/corregir`` deja una linea en
``90-sistema/correcciones.jsonl`` dentro de la boveda, que Syncthing trae
a esta PC. Este script las mergea al set, sin duplicar por mensaje.

Uso:
    uv run --env-file .env python -m tests.eval.incorporar
    uv run --env-file .env python -m tests.eval.incorporar --dry-run

Despues de correrlo: revisar las etiquetas nuevas, correr ``evaluar.py``
y commitear el set junto con el ``baseline.json`` si cambio.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from mcp_obsidian.operaciones import ruta_boveda

AQUI = Path(__file__).parent
RUTA_SET = AQUI / "mensajes.jsonl"
RUTA_CORRECCIONES = "90-sistema/correcciones.jsonl"


def _mensajes_en_set() -> set[str]:
    vistos: set[str] = set()
    for linea in RUTA_SET.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia or limpia.startswith("//"):
            continue
        vistos.add(str(json.loads(limpia)["mensaje"]))
    return vistos


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mergea /corregir al set de evaluacion")
    parser.add_argument(
        "--dry-run", action="store_true", help="Muestra que agregaria, sin escribir."
    )
    args = parser.parse_args(argv)

    correcciones = ruta_boveda() / RUTA_CORRECCIONES
    if not correcciones.exists():
        print(f"No hay correcciones en {correcciones}.")
        return 0

    ya_estan = _mensajes_en_set()
    nuevos: list[str] = []
    for linea in correcciones.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        dato = json.loads(limpia)
        mensaje = str(dato["mensaje"])
        if mensaje in ya_estan:
            continue
        ya_estan.add(mensaje)
        nuevos.append(
            json.dumps(
                {"mensaje": mensaje, "intencion": dato["intencion"], "fuente": "real"},
                ensure_ascii=False,
            )
        )

    if not nuevos:
        print("Nada nuevo para incorporar (todas las correcciones ya estan en el set).")
        return 0

    print(f"{len(nuevos)} caso(s) nuevo(s):")
    for linea in nuevos:
        print(f"  {linea}")

    if args.dry_run:
        print("\n--dry-run: no se escribio nada.")
        return 0

    with RUTA_SET.open("a", encoding="utf-8") as salida:
        for linea in nuevos:
            salida.write(linea + "\n")
    print(f"\nAgregados a {RUTA_SET.name}. Revisa las etiquetas, corre evaluar.py y commitealo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
