"""Cliente MCP (Fase 3): el puente entre los nodos del grafo y el
servidor de la boveda (``servidor.py``).

El SDK de MCP es "asincrono" (usa ``async``/``await``), pero el resto
de nuestro grafo todavia es sincronico (Fase 1 y 2 no lo necesitaron).
En vez de convertir todo el grafo a async en esta fase, esta funcion
hace de traductora: por afuera se llama como una funcion normal, por
adentro arranca y espera el mundo async con ``asyncio.run``.

Cada llamada arranca el servidor como un proceso nuevo, hace el pedido,
y lo cierra. Es mas lento que mantener una conexion abierta, pero mucho
mas simple de entender -- una optimizacion para mas adelante si hace
falta.
"""

import asyncio
import os
import sys
from typing import Any

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


class ErrorHerramientaMCP(RuntimeError):
    """El servidor MCP devolvio un error al ejecutar la herramienta."""


async def _llamar_async(nombre_herramienta: str, argumentos: dict[str, Any]) -> list[str]:
    parametros = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_obsidian.servidor"],
        # Por seguridad, MCP NO hereda todas tus variables de entorno al
        # subproceso -- hay que pasarle a mano las que necesita.
        env={"RUTA_BOVEDA_OBSIDIAN": os.environ.get("RUTA_BOVEDA_OBSIDIAN", "boveda_local")},
    )

    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            await sesion.initialize()
            resultado = await sesion.call_tool(nombre_herramienta, argumentos)

    if resultado.is_error:
        raise ErrorHerramientaMCP(f"{nombre_herramienta} fallo: {resultado.content}")

    # Si la herramienta devuelve una lista (ej: buscar_por_titulo), MCP la
    # manda como varios bloques de texto, uno por elemento -- no como un
    # solo bloque con la lista adentro. Por eso siempre devolvemos una
    # lista aca, aunque la herramienta haya devuelto un solo string.
    return [bloque.text for bloque in resultado.content if isinstance(bloque, types.TextContent)]


def llamar_herramienta(nombre_herramienta: str, **argumentos: Any) -> list[str]:
    """Version sincronica de _llamar_async -- esta es la que usan los nodos.

    Siempre devuelve una lista de strings. Si la herramienta devuelve un
    solo valor (como ``crear_nota``), va a ser una lista de un elemento.
    """
    return asyncio.run(_llamar_async(nombre_herramienta, argumentos))
