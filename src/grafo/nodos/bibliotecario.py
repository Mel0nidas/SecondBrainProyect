"""Nodo Bibliotecario (DISEÑO.md §2.2): responde consultas, solo lectura.

Desde la Fase 4, busca por significado (Chroma + embeddings de Voyage,
ver ``rag/indexar.py``) en vez de por palabras clave exactas -- esto es
lo que permite que "¿que dije sobre plata?" encuentre una nota que
habla de "presupuesto", aunque no compartan ninguna palabra. A
diferencia de las notas (que pasan por el servidor MCP), el indice de
Chroma se consulta directo: es una libreria embebida, no un servicio
externo.
"""

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado
from grafo.utilidades import cargar_prompt
from rag.indexar import buscar_semantico

MODELO_BIBLIOTECARIO = "claude-sonnet-4-6"


def bibliotecario(estado: Estado) -> dict[str, object]:
    snippets = buscar_semantico(estado.mensaje_usuario)

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
