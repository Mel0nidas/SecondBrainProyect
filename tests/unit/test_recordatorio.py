"""Tests del nodo Recordatorio. Se mockea el modelo; el almacen escribe
en una boveda temporal."""

from pathlib import Path
from unittest.mock import patch

import pytest

from grafo.estado import Estado, RecordatorioPropuesta
from grafo.nodos.recordatorio import recordatorio
from recordatorios import almacen


@pytest.fixture(autouse=True)
def _entorno(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_CHAT_ID_AUTORIZADO", "999")
    monkeypatch.setenv("TZ_USUARIO", "America/Argentina/Buenos_Aires")


def _correr(propuesta: RecordatorioPropuesta, mensaje: str) -> dict[str, object]:
    with patch("grafo.nodos.recordatorio.ChatAnthropic") as mock:
        mock.return_value.with_structured_output.return_value.invoke.return_value = propuesta
        return recordatorio(Estado(mensaje_usuario=mensaje))


def test_recordatorio_agenda_y_confirma() -> None:
    propuesta = RecordatorioPropuesta(
        entendido=True, texto="llamar al banco", cuando="2030-01-02T10:00:00"
    )
    resultado = _correr(propuesta, "recordame llamar al banco el 2 de enero de 2030")

    pend = almacen.pendientes()
    assert len(pend) == 1
    assert pend[0].texto == "llamar al banco"
    assert pend[0].chat_id == 999
    assert "llamar al banco" in str(resultado["respuesta_final"])


def test_recordatorio_sin_cuando_pide_aclaracion() -> None:
    resultado = _correr(
        RecordatorioPropuesta(entendido=False, texto="algo", cuando=""),
        "recordame algo",
    )

    assert almacen.pendientes() == []
    assert "cuándo" in str(resultado["respuesta_final"]).lower()


def test_recordatorio_en_el_pasado_se_rechaza() -> None:
    resultado = _correr(
        RecordatorioPropuesta(entendido=True, texto="algo viejo", cuando="2020-01-01T10:00:00"),
        "recordame algo el 1 de enero de 2020",
    )

    assert almacen.pendientes() == []
    assert "paso" in str(resultado["respuesta_final"]).lower()
