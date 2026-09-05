"""Servidor MCP de la boveda de Obsidian (DISEÑO.md §4.1, Fase 3).

Corre por stdio: no abre ningun puerto de red, se comunica por entrada
y salida estandar con quien lo invoque (nuestro cliente en
``cliente.py``). Cada funcion decorada con ``@mcp.tool()`` queda
publicada como una accion que un cliente MCP puede pedir por nombre.
"""

from mcp.server.mcpserver import MCPServer

from mcp_obsidian import operaciones

mcp = MCPServer("boveda-obsidian")


@mcp.tool()
def crear_nota(titulo: str, tags: list[str], contenido: str) -> str:
    """Crea una nota nueva en 00-inbox/ con frontmatter. Devuelve su ruta."""
    return operaciones.crear_nota(titulo, tags, contenido)


@mcp.tool()
def leer_nota(ruta_relativa: str) -> str:
    """Lee el contenido completo de una nota, dada su ruta relativa a la boveda."""
    return operaciones.leer_nota(ruta_relativa)


@mcp.tool()
def agregar_a_nota(ruta_relativa: str, texto: str) -> str:
    """Agrega texto al final de una nota existente."""
    return operaciones.agregar_a_nota(ruta_relativa, texto)


@mcp.tool()
def listar_carpeta(carpeta: str = "") -> list[str]:
    """Lista las rutas de las notas .md dentro de una carpeta (vacio = toda la boveda)."""
    return operaciones.listar_carpeta(carpeta)


@mcp.tool()
def buscar_por_titulo(consulta: str) -> list[str]:
    """Busca notas relacionadas con la consulta (placeholder hasta el RAG de Fase 4)."""
    return operaciones.buscar_por_titulo(consulta)


if __name__ == "__main__":
    mcp.run(transport="stdio")
