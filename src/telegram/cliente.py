"""Cliente de Telegram (DISEÑO.md §2.7, Fase 5): enviar mensajes.

Se conecta DIRECTO a la API de Telegram (no via MCP): Telegram es la
puerta de entrada del asistente, no una herramienta que un agente elija
usar o no -- por eso esta conexion es codigo Python a medida, simple,
en vez de pasar por el protocolo MCP (decision de DISEÑO.md §Parte 1).
"""

import os

import httpx

TIMEOUT_SEGUNDOS = 10.0


def _url_base() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_BOT_TOKEN.")
    return f"https://api.telegram.org/bot{token}"


def enviar_mensaje(chat_id: int, texto: str) -> None:
    """Manda un mensaje de texto a un chat de Telegram.

    Sincronica a proposito (como el resto del grafo, ver
    ``mcp_obsidian/cliente.py``): la ruta del webhook en ``app/main.py``
    corre en un thread aparte, asi que bloquear un momento acá no
    frena al servidor.
    """
    respuesta = httpx.post(
        f"{_url_base()}/sendMessage",
        json={"chat_id": chat_id, "text": texto},
        timeout=TIMEOUT_SEGUNDOS,
    )
    respuesta.raise_for_status()
