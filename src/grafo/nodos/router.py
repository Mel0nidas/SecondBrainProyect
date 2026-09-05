"""Nodo Router (DISEÑO.md §2.2): clasifica el mensaje, no hace nada mas.

Usa Haiku (no Sonnet) porque este nodo corre en el 100% de los
mensajes -- es el unico paso obligatorio siempre, asi que conviene que
sea el modelo mas barato y rapido.
"""

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado, SalidaRouter
from grafo.utilidades import cargar_prompt

# claude-haiku-4-5-20251001 es el modelo Haiku vigente al construir esto
# (ver DISEÑO.md §4.2 -- verificar en la doc de Anthropic si cambio).
MODELO_ROUTER = "claude-haiku-4-5-20251001"


def router(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_ROUTER)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(SalidaRouter)

    prompt = cargar_prompt("router")
    entrada = f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}"
    salida = modelo_estructurado.invoke(entrada)
    assert isinstance(salida, SalidaRouter)  # nos aseguramos el tipo para mypy

    return {"intencion": salida.clase}
