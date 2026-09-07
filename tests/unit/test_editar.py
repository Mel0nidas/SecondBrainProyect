"""Tests del nodo Editar."""

from unittest.mock import patch

from grafo.estado import Estado
from grafo.nodos.editar import editar


def test_editar_sin_nota_reciente_lo_dice() -> None:
    resultado = editar(Estado(mensaje_usuario="agregale que el precio era 200"))

    assert "nota reciente" in str(resultado["respuesta_final"])


def test_editar_agrega_a_la_ultima_nota_y_reindexa() -> None:
    estado = Estado(
        mensaje_usuario="agregale que el precio era 200",
        ruta_nota_creada="00-inbox/impresora-nueva.md",
    )

    with (
        patch("grafo.nodos.editar.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.editar.reindexar_nota") as reindex_mock,
    ):
        resultado = editar(estado)

    llamar_mock.assert_called_once_with(
        "agregar_a_nota", ruta_relativa="00-inbox/impresora-nueva.md", texto="el precio era 200"
    )
    reindex_mock.assert_called_once_with("00-inbox/impresora-nueva.md")
    assert resultado["ruta_nota_creada"] == "00-inbox/impresora-nueva.md"
    assert "impresora-nueva.md" in str(resultado["respuesta_final"])


def test_editar_sin_prefijo_conocido_agrega_el_mensaje_entero() -> None:
    estado = Estado(
        mensaje_usuario="viene con garantia de un año", ruta_nota_creada="00-inbox/x.md"
    )

    with (
        patch("grafo.nodos.editar.llamar_herramienta") as llamar_mock,
        patch("grafo.nodos.editar.reindexar_nota"),
    ):
        editar(estado)

    assert llamar_mock.call_args.kwargs["texto"] == "viene con garantia de un año"
