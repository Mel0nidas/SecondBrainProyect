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
