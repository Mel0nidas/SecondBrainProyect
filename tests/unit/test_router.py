"""Test del nodo Router: se mockea el modelo, no llama a la API real."""

from unittest.mock import patch

from grafo.estado import Estado, Intencion, SalidaRouter
from grafo.nodos.router import router


def test_router_devuelve_la_intencion_clasificada() -> None:
    salida_falsa = SalidaRouter(clase=Intencion.CAPTURAR, confianza=0.95)

    with patch("grafo.nodos.router.ChatAnthropic") as modelo_mock:
        estructurado = modelo_mock.return_value.with_structured_output.return_value
        estructurado.invoke.return_value = salida_falsa

        resultado = router(Estado(mensaje_usuario="guarda esta idea"))

    assert resultado["intencion"] == Intencion.CAPTURAR
