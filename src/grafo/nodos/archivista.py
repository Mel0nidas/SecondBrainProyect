"""Nodo Archivista (DISEÑO.md §2.2): escribe notas en la boveda.

En esta fase usa la boveda "falsa" (una carpeta local cualquiera, ver
``grafo/boveda_local.py``). En la Fase 3 se conecta a la boveda real de
Obsidian via MCP, pero la firma de este nodo no deberia cambiar mucho.
"""

from langchain_anthropic import ChatAnthropic

from grafo.boveda_local import crear_nota
from grafo.estado import Estado, NotaPropuesta
from grafo.utilidades import cargar_prompt

MODELO_ARCHIVISTA = "claude-sonnet-4-6"


def archivista(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_ARCHIVISTA)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(NotaPropuesta)

    prompt = cargar_prompt("archivista")
    entrada = f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}"
    propuesta = modelo_estructurado.invoke(entrada)
    assert isinstance(propuesta, NotaPropuesta)

    ruta = crear_nota(
        titulo=propuesta.titulo,
        tags=propuesta.tags,
        contenido=estado.mensaje_usuario,
    )

    return {"respuesta_final": f'Guardado como "{propuesta.titulo}" ({ruta}).'}
