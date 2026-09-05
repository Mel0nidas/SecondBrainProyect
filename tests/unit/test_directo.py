"""Tests del nodo directo (comandos fijos + los dos comandos de prueba)."""

from unittest.mock import patch

from grafo.estado import Estado
from grafo.nodos.directo import directo


def test_ayuda_responde_con_la_lista_de_comandos() -> None:
    resultado = directo(Estado(mensaje_usuario="/ayuda"))

    assert "Comandos disponibles" in str(resultado["respuesta_final"])


def test_mensaje_no_reconocido_pide_reformular() -> None:
    resultado = directo(Estado(mensaje_usuario="asdasdasd"))

    assert "reformular" in str(resultado["respuesta_final"])


def test_probar_confirmacion_confirmada() -> None:
    with patch("grafo.nodos.directo.interrupt", return_value="si") as interrupt_mock:
        resultado = directo(Estado(mensaje_usuario="/probar_confirmacion"))

    interrupt_mock.assert_called_once()
    assert "CONFIRMADA" in str(resultado["respuesta_final"])


def test_probar_confirmacion_cancelada() -> None:
    with patch("grafo.nodos.directo.interrupt", return_value="no"):
        resultado = directo(Estado(mensaje_usuario="/probar_confirmacion"))

    assert "CANCELADA" in str(resultado["respuesta_final"])
