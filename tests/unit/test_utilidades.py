"""Tests de grafo/utilidades.py: resolución de modelos por entorno (DISEÑO §4.2)."""

import pytest

from grafo import utilidades


def test_modelo_router_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODELO_ROUTER", raising=False)
    assert utilidades.modelo_router() == utilidades.MODELO_ROUTER_DEFAULT


def test_modelo_router_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELO_ROUTER", "claude-haiku-9")
    assert utilidades.modelo_router() == "claude-haiku-9"


def test_modelo_agentes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODELO_AGENTES", raising=False)
    assert utilidades.modelo_agentes() == utilidades.MODELO_AGENTES_DEFAULT


def test_modelo_agentes_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODELO_AGENTES", "claude-opus-5")
    assert utilidades.modelo_agentes() == "claude-opus-5"
