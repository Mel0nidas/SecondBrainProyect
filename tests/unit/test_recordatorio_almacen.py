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


def test_agregar_guarda_el_repetir() -> None:
    a = almacen.agregar("factura", _dt(days=1), 1, _dt(), repetir="semanal")
    assert a.repetir == "semanal"
    assert almacen.pendientes()[0].repetir == "semanal"


def test_agregar_repetir_invalido_cae_en_no() -> None:
    a = almacen.agregar("x", _dt(days=1), 1, _dt(), repetir="cada-tanto")
    assert a.repetir == "no"


def test_reprogramar_mueve_la_hora_y_deja_pendiente() -> None:
    a = almacen.agregar("regar", _dt(hours=1), 1, _dt(), repetir="diario")

    assert almacen.reprogramar(a.id, _dt(days=1, hours=1)) is True

    p = almacen.pendientes()
    assert len(p) == 1
    assert p[0].cuando_dt() == _dt(days=1, hours=1)
    assert p[0].estado == "pendiente"


def test_leer_un_recordatorio_viejo_sin_campo_repetir() -> None:
    # Simula una linea escrita antes de que existiera "repetir".
    ruta = almacen._ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        '{"id": "abc", "texto": "viejo", "cuando": "2026-09-09T12:00:00+00:00",'
        ' "chat_id": 1, "creado": "2026-09-07T12:00:00+00:00", "estado": "pendiente"}\n',
        encoding="utf-8",
    )

    p = almacen.pendientes()
    assert len(p) == 1
    assert p[0].repetir == "no"
