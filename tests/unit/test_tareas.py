"""Tests del nodo Tareas (listas). Se mockea el modelo y el reindexado; el
disco es real (boveda temporal)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from grafo.estado import Estado, OperacionLista
from grafo.nodos.tareas import tareas
from mcp_obsidian import operaciones


@pytest.fixture(autouse=True)
def _boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))


def _correr(op: OperacionLista, mensaje: str) -> tuple[dict[str, object], MagicMock]:
    """Corre el nodo con el modelo y el reindexado mockeados. Devuelve
    (resultado, mock_de_reindexar_nota)."""
    with (
        patch("grafo.nodos.tareas.ChatAnthropic") as mock,
        patch("grafo.nodos.tareas.reindexar_nota") as reindex,
    ):
        mock.return_value.with_structured_output.return_value.invoke.return_value = op
        resultado = tareas(Estado(mensaje_usuario=mensaje))
    return resultado, reindex


def test_agregar_suma_a_la_lista_y_la_muestra() -> None:
    resultado, _ = _correr(
        OperacionLista(operacion="agregar", lista="compras", items=["pan", "leche"]),
        "compra pan y leche la proxima vez que vayas al super",
    )

    texto = str(resultado["respuesta_final"])
    assert "pan" in texto and "leche" in texto
    assert operaciones.leer_lista("compras") == ["pan", "leche"]


def test_completar_marca_el_item() -> None:
    operaciones.agregar_a_lista("compras", ["pan", "leche"])

    resultado, _ = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["pan"]),
        "ya compre el pan",
    )

    assert "Marque" in str(resultado["respuesta_final"])
    assert operaciones.leer_lista("compras") == ["leche"]


def test_mostrar_devuelve_los_items_abiertos() -> None:
    operaciones.agregar_a_lista("viaje", ["cargador", "auriculares"])

    resultado, _ = _correr(
        OperacionLista(operacion="mostrar", lista="viaje", items=[]),
        "que tengo en la lista del viaje",
    )

    texto = str(resultado["respuesta_final"])
    assert "cargador" in texto and "auriculares" in texto


def test_completar_algo_que_no_esta_lo_reporta() -> None:
    operaciones.agregar_a_lista("compras", ["pan"])

    resultado, _ = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["frutillas"]),
        "ya compre las frutillas",
    )

    assert "frutillas" in str(resultado["respuesta_final"])


# --- Reindexado inmediato de la lista tocada (Fase 12 en el acto) --------


def test_agregar_items_nuevos_reindexa_la_lista() -> None:
    _, reindex = _correr(
        OperacionLista(operacion="agregar", lista="compras", items=["pan"]),
        "comprar pan",
    )

    reindex.assert_called_once_with("20-tareas/compras.md")


def test_agregar_todo_duplicado_no_reindexa() -> None:
    operaciones.agregar_a_lista("compras", ["pan"])

    _, reindex = _correr(
        OperacionLista(operacion="agregar", lista="compras", items=["pan"]),
        "comprar pan",
    )

    reindex.assert_not_called()


def test_completar_un_item_reindexa() -> None:
    operaciones.agregar_a_lista("compras", ["pan"])

    _, reindex = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["pan"]),
        "ya compre el pan",
    )

    reindex.assert_called_once_with("20-tareas/compras.md")


def test_completar_sin_match_no_reindexa() -> None:
    operaciones.agregar_a_lista("compras", ["pan"])

    _, reindex = _correr(
        OperacionLista(operacion="completar", lista="compras", items=["frutillas"]),
        "ya compre las frutillas",
    )

    reindex.assert_not_called()


def test_mostrar_no_reindexa() -> None:
    operaciones.agregar_a_lista("viaje", ["cargador"])

    _, reindex = _correr(
        OperacionLista(operacion="mostrar", lista="viaje", items=[]),
        "que tengo en la lista del viaje",
    )

    reindex.assert_not_called()


def test_si_el_reindex_falla_la_respuesta_igual_sale() -> None:
    with (
        patch("grafo.nodos.tareas.ChatAnthropic") as mock,
        patch(
            "grafo.nodos.tareas.reindexar_nota",
            side_effect=RuntimeError("rate limit simulado"),
        ),
    ):
        mock.return_value.with_structured_output.return_value.invoke.return_value = OperacionLista(
            operacion="agregar", lista="compras", items=["pan"]
        )
        resultado = tareas(Estado(mensaje_usuario="comprar pan"))

    assert "pan" in str(resultado["respuesta_final"])
    assert operaciones.leer_lista("compras") == ["pan"]
