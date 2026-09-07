"""Tests de telegram/cliente.py. Se mockea httpx -- no se manda nada real."""

from unittest.mock import MagicMock, patch

import pytest

from telegram import cliente


def test_enviar_mensaje_llama_al_endpoint_correcto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-de-prueba")

    with patch("telegram.cliente.httpx.post") as post_mock:
        post_mock.return_value = MagicMock(raise_for_status=MagicMock())

        cliente.enviar_mensaje(chat_id=123, texto="hola")

    post_mock.assert_called_once()
    url, kwargs = post_mock.call_args[0][0], post_mock.call_args[1]
    assert url == "https://api.telegram.org/bottoken-de-prueba/sendMessage"
    assert kwargs["json"] == {"chat_id": 123, "text": "hola"}


def test_enviar_mensaje_sin_token_explota_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    with pytest.raises(RuntimeError, match="TELEGRAM_BOT_TOKEN"):
        cliente.enviar_mensaje(chat_id=123, texto="hola")


def test_descargar_archivo_hace_los_dos_pedidos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Telegram exige dos pasos: preguntar la ubicacion, y despues bajar."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token-de-prueba")

    with patch("telegram.cliente.httpx.get") as get_mock:
        metadatos = MagicMock(raise_for_status=MagicMock())
        metadatos.json.return_value = {"result": {"file_path": "photos/file_1.jpg"}}
        contenido = MagicMock(raise_for_status=MagicMock(), content=b"bytes-de-la-foto")
        get_mock.side_effect = [metadatos, contenido]

        datos = cliente.descargar_archivo("ABC123")

    assert datos == b"bytes-de-la-foto"

    primera_url = get_mock.call_args_list[0][0][0]
    assert primera_url.endswith("/getFile")
    assert get_mock.call_args_list[0][1]["params"] == {"file_id": "ABC123"}

    segunda_url = get_mock.call_args_list[1][0][0]
    assert segunda_url == "https://api.telegram.org/file/bottoken-de-prueba/photos/file_1.jpg"
