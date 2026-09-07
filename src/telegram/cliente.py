"""Cliente de Telegram (DISEÑO.md §2.7): enviar mensajes y bajar archivos.

Se conecta DIRECTO a la API de Telegram (no via MCP): Telegram es la
puerta de entrada del asistente, no una herramienta que un agente elija
usar o no -- por eso esta conexion es codigo Python a medida, simple,
en vez de pasar por el protocolo MCP (decision de DISEÑO.md §Parte 1).

Desde la Fase 7 tambien baja archivos (fotos), lo que en Telegram son
siempre DOS pedidos: uno para preguntar donde quedo guardado el archivo,
y otro para bajarlo de esa ubicacion.
"""

import os

import httpx

TIMEOUT_SEGUNDOS = 10.0
# Bajar una foto tarda mas que mandar un mensaje de texto.
TIMEOUT_DESCARGA_SEGUNDOS = 60.0


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


def descargar_archivo(file_id: str) -> bytes:
    """Baja un archivo de Telegram (una foto) y devuelve sus bytes.

    Telegram no manda el archivo dentro del webhook: manda solo un
    ``file_id``. Con ese id hay que pedir primero la ubicacion interna
    ("getFile"), y recien despues bajar el contenido de esa ubicacion.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Falta la variable de entorno TELEGRAM_BOT_TOKEN.")

    metadatos = httpx.get(
        f"{_url_base()}/getFile",
        params={"file_id": file_id},
        timeout=TIMEOUT_SEGUNDOS,
    )
    metadatos.raise_for_status()
    ruta_remota = metadatos.json()["result"]["file_path"]

    contenido = httpx.get(
        f"https://api.telegram.org/file/bot{token}/{ruta_remota}",
        timeout=TIMEOUT_DESCARGA_SEGUNDOS,
    )
    contenido.raise_for_status()
    return contenido.content
