"""Tests del webhook de Telegram (app/main.py).

Se mockean: el modelo del Router (siempre corre primero, hasta para
comandos) y ``enviar_mensaje`` (no se manda nada real a Telegram). El
checkpointer usa un archivo SQLite temporal, no el del proyecto real.
"""

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from grafo.estado import Intencion, NotaImagenPropuesta, SalidaRouter

CHAT_ID_AUTORIZADO = 999
SECRET = "el-secreto-de-prueba"


@pytest.fixture(autouse=True)
def _entorno_de_prueba(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_CHECKPOINTS_SQLITE", str(tmp_path / "checkpoints.sqlite"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-de-prueba")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_CHAT_ID_AUTORIZADO", str(CHAT_ID_AUTORIZADO))


@pytest.fixture
def cliente() -> Iterator[TestClient]:
    with TestClient(app) as cliente_de_prueba:
        yield cliente_de_prueba


def _actualizacion(chat_id: int, texto: str) -> dict[str, object]:
    return {"message": {"chat": {"id": chat_id}, "text": texto}}


def _headers(secret: str | None = SECRET) -> dict[str, str]:
    return {"X-Telegram-Bot-Api-Secret-Token": secret} if secret else {}


def test_mensaje_de_chat_no_autorizado_se_ignora(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram", json=_actualizacion(111, "hola"), headers=_headers()
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()


def test_mensaje_sin_secret_correcto_se_ignora(cliente: TestClient) -> None:
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "hola"),
            headers=_headers(secret="secreto-incorrecto"),
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()


def test_comando_ayuda_responde_por_telegram(cliente: TestClient) -> None:
    salida_comando = SalidaRouter(clase=Intencion.COMANDO, confianza=0.99)

    with (
        patch("grafo.nodos.router.ChatAnthropic") as modelo_mock,
        patch("app.main.enviar_mensaje") as enviar_mock,
    ):
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_comando
        )

        respuesta = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/ayuda"),
            headers=_headers(),
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_called_once()
    chat_id_enviado, texto_enviado = enviar_mock.call_args[0]
    assert chat_id_enviado == CHAT_ID_AUTORIZADO
    assert "Comandos disponibles" in texto_enviado


def test_probar_confirmacion_pausa_y_despues_resume(cliente: TestClient) -> None:
    salida_comando = SalidaRouter(clase=Intencion.COMANDO, confianza=0.99)

    with (
        patch("grafo.nodos.router.ChatAnthropic") as modelo_mock,
        patch("app.main.enviar_mensaje") as enviar_mock,
    ):
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            salida_comando
        )

        primera = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "/probar_confirmacion"),
            headers=_headers(),
        )
        segunda = cliente.post(
            "/webhook/telegram",
            json=_actualizacion(CHAT_ID_AUTORIZADO, "si"),
            headers=_headers(),
        )

    assert primera.status_code == 200
    assert segunda.status_code == 200
    assert enviar_mock.call_count == 2

    _, texto_pregunta = enviar_mock.call_args_list[0][0]
    assert "Confirmas" in texto_pregunta

    _, texto_final = enviar_mock.call_args_list[1][0]
    assert "CONFIRMADA" in texto_final


def test_foto_se_baja_y_llega_al_grafo_como_ruta(
    cliente: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una foto se guarda en la boveda y al grafo le llega su RUTA, no los bytes.

    Es la pieza clave de la Fase 7: el estado del grafo se serializa al
    checkpointer en cada paso, asi que meterle imagenes enteras lo haria
    crecer sin control.
    """
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path / "boveda"))

    actualizacion = {
        "message": {
            "chat": {"id": CHAT_ID_AUTORIZADO},
            "caption": "pizarra de la reunion",
            # Telegram manda varios tamaños; se usa el ultimo (el mayor).
            "photo": [
                {"file_id": "chico", "width": 90},
                {"file_id": "grande", "width": 1280},
            ],
        }
    }

    # Se parchean las dependencias INTERNAS del archivista, no el nodo
    # entero: el grafo ya quedo compilado con una referencia directa a
    # la funcion cuando arranco el server, asi que parchear el nombre
    # del modulo a esta altura no tendria ningun efecto.
    with (
        patch("app.main.descargar_archivo") as descargar_mock,
        patch("app.main.enviar_mensaje"),
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
    ):
        descargar_mock.return_value = b"bytes-de-la-foto"
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = (
            NotaImagenPropuesta(
                titulo="Pizarra",
                tags=["reunion"],
                transcripcion="lo que se lee",
                descripcion="una pizarra",
            )
        )
        llamar_mock.return_value = ["30-imagenes/pizarra.md"]

        respuesta = cliente.post(
            "/webhook/telegram", json=actualizacion, headers=_headers()
        )

    assert respuesta.status_code == 200

    # Se bajo el tamaño MAS GRANDE, no el primero de la lista.
    descargar_mock.assert_called_once_with("grande")

    # Y la foto quedo escrita en la carpeta que manda el diseño (§2.5).
    guardadas = list((tmp_path / "boveda" / "30-imagenes").iterdir())
    assert len(guardadas) == 1
    assert guardadas[0].read_bytes() == b"bytes-de-la-foto"


def test_mensaje_sin_foto_ni_texto_no_rompe(cliente: TestClient) -> None:
    """Un update raro (ej: una reaccion) se ignora sin explotar."""
    with patch("app.main.enviar_mensaje") as enviar_mock:
        respuesta = cliente.post(
            "/webhook/telegram", json={"edited_message": {}}, headers=_headers()
        )

    assert respuesta.status_code == 200
    enviar_mock.assert_not_called()
