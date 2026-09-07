"""Tests del Digestor semanal. Se mockea el modelo; el disco es real."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from digestor import digestor
from digestor.digestor import SintesisSemanal
from mcp_obsidian import operaciones


@pytest.fixture(autouse=True)
def _boveda(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))


def _mock_sintesis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        digestor,
        "_sintetizar",
        lambda notas: SintesisSemanal(
            temas=f"Esta semana guardaste {len(notas)} cosas sobre varios temas.",
            sugerencia="Conecta las notas relacionadas.",
        ),
    )


def _nota_con_fecha(carpeta: str, nombre: str, fecha: date, cuerpo: str) -> None:
    ruta = Path(operaciones.ruta_boveda()) / carpeta
    ruta.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\nfecha: {fecha.isoformat()}\norigen: telegram\ntags: []\n---\n"
    (ruta / f"{nombre}.md").write_text(
        f"{frontmatter}\n# {nombre}\n\n{cuerpo}", encoding="utf-8"
    )


def test_digest_junta_semana_inbox_viejo_y_listas(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_sintesis(monkeypatch)
    hoy = datetime(2026, 9, 8, 9, 0)

    _nota_con_fecha("00-inbox", "idea-de-esta-semana", hoy.date() - timedelta(days=2), "algo nuevo")
    _nota_con_fecha("00-inbox", "cosa-vieja", hoy.date() - timedelta(days=30), "quedo aca")
    operaciones.agregar_a_lista("compras", ["pan", "cafe"])

    texto = digestor.generar_digest(hoy)

    assert texto is not None
    assert "1 nota" in texto  # una de la semana
    assert "cosa-vieja" in texto  # inbox viejo
    assert "compras (2)" in texto
    # y dejo la nota del repaso en 90-sistema/
    guardadas = list((Path(operaciones.ruta_boveda()) / "90-sistema").glob("*.md"))
    assert len(guardadas) == 1


def test_digest_sin_notas_de_la_semana_no_llama_al_modelo(monkeypatch: pytest.MonkeyPatch) -> None:
    def _explota(_notas: object) -> object:
        raise AssertionError("no deberia sintetizar sin notas de la semana")

    monkeypatch.setattr(digestor, "_sintetizar", _explota)
    operaciones.agregar_a_lista("compras", ["pan"])

    texto = digestor.generar_digest(datetime(2026, 9, 8, 9, 0))

    assert texto is not None
    assert "no guardaste nada nuevo" in texto
    assert "compras (1)" in texto


def test_digest_vacio_devuelve_none() -> None:
    assert digestor.generar_digest(datetime(2026, 9, 8, 9, 0)) is None
