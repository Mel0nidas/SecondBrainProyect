"""Tests de transcripcion/groq.py. Se mockea httpx -- no se llama a Groq."""

from unittest.mock import MagicMock, patch

import pytest

from transcripcion import groq


def test_transcribir_manda_el_audio_y_devuelve_el_texto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")

    with patch("transcripcion.groq.httpx.post") as post_mock:
        post_mock.return_value = MagicMock(
            raise_for_status=MagicMock(),
            json=MagicMock(return_value={"text": "  hola que tal  "}),
        )

        texto = groq.transcribir(b"bytes-del-audio", nombre_archivo="audio.ogg")

    # Se recorta el espacio de sobra que suele devolver Whisper.
    assert texto == "hola que tal"

    post_mock.assert_called_once()
    url = post_mock.call_args[0][0]
    kwargs = post_mock.call_args[1]

    assert url == groq.URL_TRANSCRIPCION
    assert kwargs["headers"]["Authorization"] == "Bearer clave-de-prueba"
    assert kwargs["files"]["file"][0] == "audio.ogg"
    assert kwargs["files"]["file"][1] == b"bytes-del-audio"
    assert kwargs["data"]["model"] == groq.MODELO_TRANSCRIPCION
    assert kwargs["data"]["language"] == "es"


def test_transcribir_sin_api_key_explota_claro(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        groq.transcribir(b"bytes-del-audio")
