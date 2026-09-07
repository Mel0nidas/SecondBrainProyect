"""Tests del registro de costos."""

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from costos import registro


@pytest.fixture(autouse=True)
def _boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))


def test_registrar_uso_escribe_una_linea() -> None:
    registro.registrar_uso(
        "claude-haiku-4-5-20251001", {"input_tokens": 1200, "output_tokens": 30}, "router"
    )

    linea = json.loads(registro._ruta().read_text(encoding="utf-8").splitlines()[0])
    assert linea["modelo"].startswith("claude-haiku-4-5")
    assert linea["in"] == 1200 and linea["out"] == 30
    assert linea["etiqueta"] == "router"


def test_registrar_uso_ignora_metadata_ausente() -> None:
    registro.registrar_uso("claude-sonnet-4-6", None, "archivista")
    registro.registrar_uso("claude-sonnet-4-6", {"input_tokens": 0, "output_tokens": 0}, "x")
    assert not registro._ruta().exists()


def test_extraer_saca_parsed_y_registra_del_raw() -> None:
    salida = {
        "parsed": SimpleNamespace(clase="capturar"),
        "raw": SimpleNamespace(usage_metadata={"input_tokens": 500, "output_tokens": 12}),
    }

    parsed = registro.extraer(salida, "claude-haiku-4-5", "router")

    assert parsed.clase == "capturar"
    linea = json.loads(registro._ruta().read_text(encoding="utf-8").splitlines()[0])
    assert linea["in"] == 500


def test_extraer_con_objeto_pelado_no_registra() -> None:
    obj = SimpleNamespace(clase="tarea")
    assert registro.extraer(obj, "claude-haiku-4-5", "router") is obj
    assert not registro._ruta().exists()


def test_resumen_suma_por_modelo_y_aplica_precio() -> None:
    # 1M tokens de entrada de Sonnet 4.6 = USD 3.00; 100k de salida = USD 1.50.
    registro.registrar_uso(
        "claude-sonnet-4-6", {"input_tokens": 1_000_000, "output_tokens": 100_000}, "archivista"
    )
    registro.registrar_uso(
        "claude-haiku-4-5-20251001", {"input_tokens": 200_000, "output_tokens": 5_000}, "router"
    )

    texto = registro.resumen(dias=30)

    assert "claude-sonnet-4-6" in texto
    assert "USD 4.50" in texto  # 3.00 + 1.50 de Sonnet
    assert "Total LLM: USD 4.7" in texto  # 4.50 + 0.225 de Haiku
    assert "Infra AWS" in texto


def test_resumen_respeta_la_ventana_de_dias() -> None:
    ruta = registro._ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    viejo = (date.today() - timedelta(days=60)).isoformat()
    ruta.write_text(
        json.dumps({"fecha": viejo, "modelo": "claude-sonnet-4-6", "in": 9_000_000, "out": 0})
        + "\n",
        encoding="utf-8",
    )

    assert "Sin llamadas" in registro.resumen(dias=30)


def test_resumen_sin_archivo() -> None:
    assert "Todavia no hay datos" in registro.resumen()
