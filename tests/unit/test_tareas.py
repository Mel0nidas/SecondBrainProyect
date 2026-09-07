"""Tests del nodo Tareas (listas). Se mockea el modelo; el disco es real
(boveda temporal)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from grafo.estado import Estado, OperacionLista
from grafo.nodos.tareas import tareas
from mcp_obsidian import operaciones


@pytest.fixture(autouse=True)
def _boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))


def _correr(op: OperacionLista, mensaje: str) -> dict[str, object]:
    with patch("grafo.nodos.tareas.ChatAnthropic") as mock:
        mock.return_value.with_structured_output.return_value.invoke.return_value = op
        return tareas(Estado(mensaje_usuario=mensaje))


def test_agregar_suma_a_la_lista_y_la_muestra() -> None:
    resultado = _correr(
        OperacionLista(operacion="agregar", lista="compras", items=["pan", "leche"]),
        "compra pan y leche la proxima vez que vayas al super",
    )

    texto = str(resultado["respuesta_final"])
    assert "pan" in texto and "leche" in texto
    assert operaciones.leer_lista("compras") == ["pan", "leche"]


def test_completar_marca_el_item() -> None:
    operaciones.agregar_a_lista("compras", ["pan", "leche"])

    resultado = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["pan"]),
        "ya compre el pan",
    )

    assert "Marque" in str(resultado["respuesta_final"])
    assert operaciones.leer_lista("compras") == ["leche"]


def test_mostrar_devuelve_los_items_abiertos() -> None:
    operaciones.agregar_a_lista("viaje", ["cargador", "auriculares"])

    resultado = _correr(
        OperacionLista(operacion="mostrar", lista="viaje", items=[]),
        "que tengo en la lista del viaje",
    )

    texto = str(resultado["respuesta_final"])
    assert "cargador" in texto and "auriculares" in texto


def test_completar_algo_que_no_esta_lo_reporta() -> None:
    operaciones.agregar_a_lista("compras", ["pan"])

    resultado = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["frutillas"]),
        "ya compre las frutillas",
    )

    assert "frutillas" in str(resultado["respuesta_final"])
