"""Test del corte por presupuesto, usando el grafo completo.

Se mockea el Router (siempre clasifica como "comando"). El resto del
camino -- verificar_presupuesto <-> directo, repetido -- no llama a
Claude en ningun momento (ver directo.py), asi que corre real.
"""

from unittest.mock import patch

from grafo.estado import Estado, Intencion, Presupuesto, SalidaRouter
from grafo.grafo import construir_grafo


def test_test_loop_se_corta_por_presupuesto() -> None:
    salida_falsa = SalidaRouter(clase=Intencion.COMANDO, confianza=1.0)

    with patch("grafo.nodos.router.ChatAnthropic") as modelo_mock:
        estructurado = modelo_mock.return_value.with_structured_output.return_value
        estructurado.invoke.return_value = salida_falsa

        grafo = construir_grafo()
        resultado = grafo.invoke(
            Estado(mensaje_usuario="/test_loop"),
            config={"recursion_limit": 100},
        )

    respuesta = resultado["respuesta_final"]
    assert isinstance(respuesta, str)
    assert "Corte por presupuesto" in respuesta

    presupuesto = resultado["presupuesto"]
    assert isinstance(presupuesto, Presupuesto)
    assert presupuesto.pasos_usados == presupuesto.pasos_maximos
