"""Nodo Archivista (DISEÑO.md §2.2): escribe notas en la boveda.

Desde la Fase 3, escribe en la boveda REAL de Obsidian, a traves del
cliente MCP (no toca archivos directamente -- eso ahora es trabajo del
servidor MCP, ver ``mcp_obsidian/servidor.py``).
"""

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado, NotaPropuesta
from grafo.utilidades import cargar_prompt
from mcp_obsidian.cliente import llamar_herramienta

MODELO_ARCHIVISTA = "claude-sonnet-4-6"


def archivista(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_ARCHIVISTA)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(NotaPropuesta)

    prompt = cargar_prompt("archivista")
    entrada = f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}"
    propuesta = modelo_estructurado.invoke(entrada)
    assert isinstance(propuesta, NotaPropuesta)

    resultado = llamar_herramienta(
        "crear_nota",
        titulo=propuesta.titulo,
        tags=propuesta.tags,
        contenido=estado.mensaje_usuario,
    )
    ruta = resultado[0]

    return {"respuesta_final": f'Guardado como "{propuesta.titulo}" ({ruta}).'}
