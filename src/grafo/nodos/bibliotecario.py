"""Nodo Bibliotecario (DISEÑO.md §2.2): responde consultas, solo lectura.

Desde la Fase 4, busca por significado (Chroma + embeddings de Voyage,
ver ``rag/indexar.py``) en vez de por palabras clave exactas -- esto es
lo que permite que "¿que dije sobre plata?" encuentre una nota que
habla de "presupuesto", aunque no compartan ninguna palabra. A
diferencia de las notas (que pasan por el servidor MCP), el indice de
Chroma se consulta directo: es una libreria embebida, no un servicio
externo.

Desde la Fase 16 devuelve tambien la FUENTE: cada fragmento viene
numerado con la nota de la que salio, y la respuesta termina con un
"Fuentes: [[nota]]" para que Melo pueda ir a la nota en Obsidian.
"""

from pathlib import Path

from langchain_anthropic import ChatAnthropic

from costos import registro as costos
from grafo.estado import Estado
from grafo.utilidades import cargar_prompt, modelo_agentes
from rag.indexar import Fragmento, buscar_con_fuente

MODELO_BIBLIOTECARIO = modelo_agentes()


def _fuentes(fragmentos: list[Fragmento]) -> str:
    vistas: list[str] = []
    for f in fragmentos:
        nombre = f.titulo or (Path(f.ruta).stem if f.ruta else "")
        if nombre and nombre not in vistas:
            vistas.append(nombre)
    return ", ".join(f"[[{n}]]" for n in vistas)


def bibliotecario(estado: Estado) -> dict[str, object]:
    fragmentos = buscar_con_fuente(estado.mensaje_usuario)

    if not fragmentos:
        return {
            "snippets": [],
            "respuesta_final": "No encontre nada guardado relacionado con eso todavia.",
        }

    modelo = ChatAnthropic(model=MODELO_BIBLIOTECARIO)  # type: ignore[call-arg]
    prompt = cargar_prompt("bibliotecario")
    bloques = "\n\n---\n\n".join(
        f"[{i}] nota: {f.titulo or f.ruta}\n{f.texto}" for i, f in enumerate(fragmentos, start=1)
    )
    respuesta = modelo.invoke(
        f"{prompt}\n\nFragmentos encontrados:\n{bloques}\n\nPregunta: {estado.mensaje_usuario}"
    )
    costos.registrar_uso(
        MODELO_BIBLIOTECARIO, getattr(respuesta, "usage_metadata", None), "bibliotecario"
    )

    texto = str(respuesta.content)
    fuentes = _fuentes(fragmentos)
    if fuentes:
        texto = f"{texto}\n\nFuentes: {fuentes}"

    return {"snippets": [f.texto for f in fragmentos], "respuesta_final": texto}
