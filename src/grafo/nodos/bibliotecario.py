"""Nodo Bibliotecario (DISEÑO.md §2.2): responde consultas, solo lectura.

Desde la Fase 3, busca en la boveda REAL de Obsidian via el cliente
MCP. La busqueda semantica real (Chroma + embeddings) todavia no existe
-- eso llega en la Fase 4. Por ahora usa "buscar_por_titulo" del
servidor MCP, que es una busqueda simple por palabras clave.
"""

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado
from grafo.utilidades import cargar_prompt
from mcp_obsidian.cliente import llamar_herramienta

MODELO_BIBLIOTECARIO = "claude-sonnet-4-6"


def bibliotecario(estado: Estado) -> dict[str, object]:
    snippets = llamar_herramienta("buscar_por_titulo", consulta=estado.mensaje_usuario)

    if not snippets:
        return {
            "snippets": [],
            "respuesta_final": "No encontre nada guardado relacionado con eso todavia.",
        }

    modelo = ChatAnthropic(model=MODELO_BIBLIOTECARIO)  # type: ignore[call-arg]
    prompt = cargar_prompt("bibliotecario")
    contexto = "\n\n---\n\n".join(snippets)
    respuesta = modelo.invoke(
        f"{prompt}\n\nFragmentos encontrados:\n{contexto}\n\nPregunta: {estado.mensaje_usuario}"
    )

    return {"snippets": snippets, "respuesta_final": str(respuesta.content)}
