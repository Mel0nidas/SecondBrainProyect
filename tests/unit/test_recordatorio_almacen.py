"""Tests del almacen de recordatorios (JSONL en la boveda)."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from recordatorios import almacen


@pytest.fixture(autouse=True)
def _boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))


def _dt(**delta: float) -> datetime:
    return datetime(2026, 9, 7, 12, 0, tzinfo=UTC) + timedelta(**delta)


def test_agregar_y_listar_pendientes() -> None:
    almacen.agregar("llamar al banco", _dt(hours=2), chat_id=999, ahora_utc=_dt())
    almacen.agregar("sacar la basura", _dt(days=1), chat_id=999, ahora_utc=_dt())

    pend = almacen.pendientes()
    assert {r.texto for r in pend} == {"llamar al banco", "sacar la basura"}
    assert all(r.estado == "pendiente" for r in pend)
    assert len({r.id for r in pend}) == 2  # ids distintos


def test_vencidos_solo_devuelve_los_que_ya_pasaron() -> None:
    almacen.agregar("ya", _dt(minutes=-1), chat_id=1, ahora_utc=_dt(hours=-1))
    almacen.agregar("todavia no", _dt(hours=3), chat_id=1, ahora_utc=_dt())

    vencidos = almacen.vencidos(_dt())

    assert [r.texto for r in vencidos] == ["ya"]


def test_marcar_enviado_saca_de_pendientes_y_no_toca_los_otros() -> None:
    a = almacen.agregar("uno", _dt(hours=1), chat_id=1, ahora_utc=_dt())
    almacen.agregar("dos", _dt(hours=2), chat_id=1, ahora_utc=_dt())

    assert almacen.marcar_enviado(a.id) is True

    pend = almacen.pendientes()
    assert [r.texto for r in pend] == ["dos"]
    # "uno" sigue en el archivo, pero como "enviado".
    todos = almacen._leer_todos()
    assert {(r.texto, r.estado) for r in todos} == {("uno", "enviado"), ("dos", "pendiente")}


def test_marcar_cancelado_de_id_inexistente_devuelve_false() -> None:
    assert almacen.marcar_cancelado("nope") is False


def test_cancelar_uno_ya_enviado_no_hace_nada() -> None:
    a = almacen.agregar("x", _dt(hours=1), chat_id=1, ahora_utc=_dt())
    almacen.marcar_enviado(a.id)

    assert almacen.marcar_cancelado(a.id) is False
