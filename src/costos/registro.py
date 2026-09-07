"""Registro de costos de LLM (Fase 15).

Cada llamada a un modelo (Claude, o los embeddings de Voyage) deja una
linea en ``90-sistema/costos.jsonl`` con los tokens usados. ``/costos``
lee ese log, lo suma por modelo y lo multiplica por el precio vigente.

Precios: primera fuente Anthropic (API skill, cache 2026-06-24). Si
Anthropic los cambia, actualizar ``PRECIOS`` acá. Voyage y Groq entran
en tier gratuito a este volumen, se muestran como referencia.
"""

import json
import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from mcp_obsidian.operaciones import ruta_boveda

logger = logging.getLogger(__name__)

RUTA_RELATIVA = "90-sistema/costos.jsonl"

# (USD por millon de tokens de entrada, USD por millon de salida).
# El match es por prefijo: "claude-haiku-4-5-20251001" cae en "claude-haiku-4-5".
PRECIOS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),  # historico: los agentes usaron 4-6 hasta la Fase 15
    "voyage-3.5-lite": (0.02, 0.02),  # 200M tokens gratis en la serie voyage-3
}

# Estimacion del costo fijo de infra AWS por mes, FUERA del Free Tier
# (EC2 t3.micro ~7.5 + EBS 20GB gp3 ~1.6 + ECR ~0.3). Dentro del Free
# Tier de los primeros 12 meses es ~0.
AWS_FIJO_USD_MES = 9.0


def _ruta() -> Path:
    return ruta_boveda() / RUTA_RELATIVA


def _precio(modelo: str) -> tuple[float, float] | None:
    for prefijo, precio in PRECIOS.items():
        if modelo.startswith(prefijo):
            return precio
    return None


def _append(modelo: str, entrada_tok: int, salida_tok: int, etiqueta: str) -> None:
    if not modelo or (entrada_tok == 0 and salida_tok == 0):
        return
    try:
        ruta = _ruta()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        linea = json.dumps(
            {
                "fecha": date.today().isoformat(),
                "modelo": modelo,
                "in": int(entrada_tok),
                "out": int(salida_tok),
                "etiqueta": etiqueta,
            }
        )
        with ruta.open("a", encoding="utf-8") as salida:
            salida.write(linea + "\n")
    except Exception:
        # El tracking de costos nunca debe romper una respuesta al usuario.
        logger.exception("No se pudo registrar el costo de %s", etiqueta)


def registrar_uso(modelo: str, usage_metadata: Any, etiqueta: str) -> None:
    """Para llamadas ``.invoke()`` planas (el Bibliotecario). ``usage_metadata``
    es el dict que trae el ``AIMessage`` de LangChain, o None."""
    if not isinstance(usage_metadata, dict):
        return
    _append(
        modelo,
        int(usage_metadata.get("input_tokens", 0) or 0),
        int(usage_metadata.get("output_tokens", 0) or 0),
        etiqueta,
    )


def extraer(salida: Any, modelo: str, etiqueta: str) -> Any:
    """Para ``with_structured_output(..., include_raw=True)``.

    Si ``salida`` es el dict ``{"raw", "parsed", ...}``, registra los
    tokens del ``raw`` y devuelve ``parsed``. Si es un objeto pelado
    (por ejemplo un mock en los tests), lo devuelve tal cual sin registrar.
    """
    if isinstance(salida, dict) and "parsed" in salida:
        raw = salida.get("raw")
        registrar_uso(modelo, getattr(raw, "usage_metadata", None), etiqueta)
        return salida["parsed"]
    return salida


def _formato_usd(valor: float) -> str:
    return f"USD {valor:.2f}" if valor >= 0.01 else "USD <0.01"


def resumen(dias: int = 30) -> str:
    """Texto para el comando ``/costos``: gasto de LLM de los ultimos N dias."""
    ruta = _ruta()
    if not ruta.exists():
        return "Todavia no hay datos de costo (no se registro ninguna llamada al modelo)."

    corte = date.today() - timedelta(days=dias)
    por_modelo: dict[str, list[int]] = {}
    dias_con_datos: set[str] = set()
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        d = json.loads(limpia)
        try:
            fecha = date.fromisoformat(d["fecha"])
        except (KeyError, ValueError):
            continue
        if fecha < corte:
            continue
        dias_con_datos.add(d["fecha"])
        acc = por_modelo.setdefault(d["modelo"], [0, 0])
        acc[0] += int(d.get("in", 0))
        acc[1] += int(d.get("out", 0))

    if not por_modelo:
        return f"Sin llamadas al modelo en los ultimos {dias} dias."

    lineas = [f"Costos LLM (ultimos {dias} dias)", ""]
    total = 0.0
    for modelo, (ent, sal) in sorted(por_modelo.items()):
        resumen_tok = f"{ent // 1000}k in / {sal // 1000}k out"
        precio = _precio(modelo)
        if precio is None:
            lineas.append(f"  {modelo}: {resumen_tok} (precio desconocido)")
            continue
        costo = ent / 1_000_000 * precio[0] + sal / 1_000_000 * precio[1]
        total += costo
        nota = "  (tier gratuito)" if modelo.startswith("voyage") else ""
        lineas.append(f"  {modelo}: {resumen_tok}  ->  {_formato_usd(costo)}{nota}")

    lineas += ["", f"Total LLM: {_formato_usd(total)}"]
    if dias_con_datos:
        promedio = total / len(dias_con_datos)
        lineas.append(
            f"Promedio por dia activo: {_formato_usd(promedio)}  ->  "
            f"~{_formato_usd(promedio * 30)}/mes"
        )
    lineas += [
        "",
        f"Infra AWS (fijo, estimado): ~USD {AWS_FIJO_USD_MES:.0f}/mes fuera del Free Tier "
        "(EC2 + EBS + ECR). Groq y Voyage: $0 al volumen actual.",
    ]
    return "\n".join(lineas)
