"""Tests de la rama de imagen del Archivista (Fase 7).

Se mockean el modelo (Claude con vision), el cliente MCP y la
indexacion. La imagen SI se escribe de verdad, en una boveda temporal:
hace falta que exista en disco porque el nodo la lee para mandarsela al
modelo.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from grafo.estado import Estado, NotaImagenPropuesta
from grafo.nodos.archivista import _armar_cuerpo, archivista

PROPUESTA = NotaImagenPropuesta(
    titulo="Pizarra de arquitectura",
    tags=["arquitectura", "reunion"],
    transcripcion="Router -> Archivista\nRouter -> Bibliotecario",
    descripcion="Foto de una pizarra con el diagrama de agentes.",
)


@pytest.fixture
def boveda_con_imagen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))
    carpeta = tmp_path / "30-imagenes"
    carpeta.mkdir(parents=True)
    (carpeta / "foto.jpg").write_bytes(b"bytes-de-prueba")
    return "30-imagenes/foto.jpg"


def test_archivista_con_imagen_crea_nota_en_carpeta_de_imagenes(boveda_con_imagen: str) -> None:
    with (
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota") as indexar_mock,
    ):
        modelo_mock.return_value.with_structured_output.return_value.invoke.return_value = PROPUESTA
        llamar_mock.return_value = ["30-imagenes/pizarra-de-arquitectura.md"]

        resultado = archivista(Estado(mensaje_usuario="", ruta_imagen=boveda_con_imagen))

    kwargs = llamar_mock.call_args.kwargs
    assert kwargs["carpeta"] == "30-imagenes"
    assert kwargs["origen"] == "telegram-imagen"
    assert kwargs["titulo"] == "Pizarra de arquitectura"

    # La nota indexada es la que tiene la transcripcion: asi la foto se
    # vuelve encontrable despues por busqueda semantica.
    assert "Router -> Archivista" in indexar_mock.call_args.kwargs["contenido"]

    assert "Pizarra de arquitectura" in str(resultado["respuesta_final"])


def test_archivista_con_imagen_manda_la_foto_al_modelo(boveda_con_imagen: str) -> None:
    with (
        patch("grafo.nodos.archivista.ChatAnthropic") as modelo_mock,
        patch("grafo.nodos.archivista.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.archivista.indexar_nota"),
    ):
        estructurado = modelo_mock.return_value.with_structured_output.return_value
        estructurado.invoke.return_value = PROPUESTA
        llamar_mock.return_value = ["30-imagenes/nota.md"]

        archivista(Estado(mensaje_usuario="", ruta_imagen=boveda_con_imagen))

    mensaje = estructurado.invoke.call_args[0][0]
    bloques = mensaje[0]["content"]
    bloque_imagen = next(b for b in bloques if b["type"] == "image")

    assert bloque_imagen["mime_type"] == "image/jpeg"
    # "bytes-de-prueba" codificado en base64.
    assert bloque_imagen["base64"] == "Ynl0ZXMtZGUtcHJ1ZWJh"


def test_cuerpo_incluye_link_a_la_imagen_y_transcripcion() -> None:
    cuerpo = _armar_cuerpo(PROPUESTA, "30-imagenes/foto.jpg", "")

    assert cuerpo.startswith("![[foto.jpg]]")
    assert "## Transcripción" in cuerpo
    assert "Router -> Bibliotecario" in cuerpo


def test_cuerpo_incluye_el_pie_de_foto_si_lo_hay() -> None:
    cuerpo = _armar_cuerpo(PROPUESTA, "30-imagenes/foto.jpg", "de la reunion del lunes")

    assert "> de la reunion del lunes" in cuerpo


def test_cuerpo_sin_transcripcion_no_pone_el_encabezado() -> None:
    sin_texto = PROPUESTA.model_copy(update={"transcripcion": "   "})

    cuerpo = _armar_cuerpo(sin_texto, "30-imagenes/foto.jpg", "")

    assert "## Transcripción" not in cuerpo
