"""Test de integracion del servidor MCP (DISEÑO.md, Fase 3: "tests del
server sin LLM, llamadas MCP directas").

A diferencia de test_mcp_operaciones.py, esto SI levanta el servidor
real como subproceso y le habla por el protocolo MCP de verdad (via
``cliente.llamar_herramienta``). No hay ningun LLM de por medio: solo
prueba que el cableado cliente <-> servidor <-> disco funciona.

Es mas lento que los demas tests (arranca un proceso de Python nuevo
por cada llamada), pero sigue corriendo en segundos.
"""

from pathlib import Path

import pytest

from mcp_obsidian.cliente import llamar_herramienta


def test_crear_y_despues_buscar_via_mcp_real(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RUTA_BOVEDA_OBSIDIAN", str(tmp_path))

    resultado_crear = llamar_herramienta(
        "crear_nota",
        titulo="Nota de integracion",
        tags=["prueba"],
        contenido="Contenido de la nota de integracion MCP.",
    )
    assert len(resultado_crear) == 1
    ruta_relativa = resultado_crear[0]
    assert (tmp_path / ruta_relativa).exists()

    encontradas = llamar_herramienta("buscar_por_titulo", consulta="integracion")
    assert len(encontradas) == 1
    assert "integracion" in encontradas[0]

    listado = llamar_herramienta("listar_carpeta", carpeta="00-inbox")
    assert ruta_relativa in listado
