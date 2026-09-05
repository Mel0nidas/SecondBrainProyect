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
from grafo.estado import Intencion, SalidaRouter

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
