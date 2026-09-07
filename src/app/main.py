"""FastAPI: webhook de Telegram (DISEÑO.md §2.7 y §5, Fase 5).

Unico punto de entrada real del asistente (antes solo existia la CLI de
las Fases 1-4, ver ``grafo/__main__.py``). Recibe los mensajes que
Telegram manda por webhook, valida que sean de la unica persona
autorizada, los pasa por el grafo, y devuelve la respuesta por el mismo
canal.

Un "webhook" es al reves de como uno suele pedir datos: en vez de que
nuestro servidor le pregunte a Telegram "¿hay mensajes nuevos?" cada
tanto, le decimos a Telegram de antemano "cuando llegue un mensaje,
avisale a esta URL" -- y Telegram nos hace un POST solo cuando hay algo
nuevo.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from grafo.estado import Estado
from grafo.grafo import construir_grafo
from mcp_obsidian import operaciones
from telegram.cliente import descargar_archivo, enviar_mensaje
from transcripcion.groq import transcribir

# Se llama ACA, al importar el modulo -- es decir, apenas arranca
# uvicorn, antes de que se procese ningun pedido. Si se llamara mas
# tarde (por ejemplo dentro de una funcion), podria ser demasiado
# tarde para variables que se leen durante el arranque del servidor,
# como la ruta del checkpointer de SQLite.
load_dotenv()


def _ruta_checkpoints() -> str:
    return os.environ.get("RUTA_CHECKPOINTS_SQLITE", "grafo_checkpoints.sqlite")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arma el grafo UNA sola vez, cuando arranca el servidor.

    El checkpointer de SQLite es lo que permite que ``interrupt()``
    pause una ejecucion y la retome en un pedido HTTP completamente
    distinto (quizas minutos despues, o incluso si el servidor se
    reinicio en el medio) -- sin el, cada mensaje de Telegram arrancaria
    de cero, sin memoria del anterior.
    """
    with SqliteSaver.from_conn_string(_ruta_checkpoints()) as checkpointer:
        app.state.grafo = construir_grafo(checkpointer=checkpointer)
        yield


app = FastAPI(lifespan=lifespan)


def _autorizado(chat_id: int, secret_recibido: str | None) -> bool:
    """Valida que el mensaje sea de Telegram Y de la unica persona autorizada.

    DISEÑO.md §2.4.4: "cualquier otro remitente se ignora (ni se loguea
    el contenido)" -- por eso esta funcion no imprime nada sobre el
    chat_id ni el mensaje cuando la validacion falla.
    """
    secret_esperado = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    chat_id_autorizado = os.environ.get("TELEGRAM_CHAT_ID_AUTORIZADO")

    if not secret_esperado or secret_recibido != secret_esperado:
        return False
    if not chat_id_autorizado or str(chat_id) != chat_id_autorizado:
        return False
    return True


def _bajar_imagen_si_hay(mensaje: dict[str, Any]) -> str | None:
    """Si el mensaje trae una imagen, la baja y la guarda en la boveda.

    Devuelve la ruta relativa dentro de la boveda, o None si el mensaje
    no traia ninguna imagen.

    Telegram manda una imagen de dos formas distintas:

    - ``photo``: la foto comprimida (lo normal). Viene en varios tamaños,
      del mas chico al mas grande; se usa el ultimo (mayor resolucion)
      porque da mejor transcripcion al pasarlo por vision.
    - ``document``: la imagen SIN comprimir, cuando el usuario elige
      "enviar como archivo". Hay que mirar el ``mime_type`` para
      distinguir una imagen de un PDF o cualquier otro adjunto.
    """
    fotos = mensaje.get("photo")
    if fotos:
        datos = descargar_archivo(fotos[-1]["file_id"])
        return operaciones.guardar_imagen(datos)

    documento = mensaje.get("document") or {}
    mime = documento.get("mime_type", "")
    if mime.startswith("image/"):
        datos = descargar_archivo(documento["file_id"])
        # "image/svg+xml" -> "svg"; "image/jpeg" se guarda como ".jpg".
        extension = mime.split("/", 1)[1].split("+", 1)[0]
        if extension == "jpeg":
            extension = "jpg"
        return operaciones.guardar_imagen(datos, extension=extension)

    return None


def _transcribir_audio_si_hay(mensaje: dict[str, Any]) -> str | None:
    """Si el mensaje trae una nota de voz o un audio, lo transcribe.

    Devuelve el texto dicho, o None si no habia audio. De ahi en mas ese
    texto sigue el mismo camino que si el usuario lo hubiera tipeado
    (DISEÑO.md §FASE 7.5): no hace falta ningun nodo nuevo.

    - ``voice``: la nota de voz del boton del microfono (OGG/Opus).
    - ``audio``: un archivo de audio mandado como tal (mp3, m4a, etc.).
    """
    audio = mensaje.get("voice") or mensaje.get("audio")
    if not audio:
        return None

    datos = descargar_archivo(audio["file_id"])
    nombre = audio.get("file_name") or _nombre_audio(audio.get("mime_type", ""))
    return transcribir(datos, nombre_archivo=nombre)


def _nombre_audio(mime_type: str) -> str:
    """Nombre ficticio con la extension que Groq usa para reconocer el formato.

    Groq mira la extension del nombre, no el contenido: si no coincide con
    un formato que soporta, rechaza el archivo. Las notas de voz de
    Telegram (``audio/ogg``) caen en el default.
    """
    subtipo = mime_type.rsplit("/", 1)[-1]
    extension = {"mpeg": "mp3", "mp4": "m4a", "x-m4a": "m4a"}.get(subtipo, "ogg")
    return f"audio.{extension}"


@app.get("/salud")
def salud() -> dict[str, str]:
    """Healthcheck simple: confirma que el servidor esta arriba."""
    return {"estado": "ok"}


@app.post("/webhook/telegram")
def webhook_telegram(
    request: Request,
    actualizacion: dict[str, Any],
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Recibe un mensaje de Telegram, lo procesa, y responde por el mismo chat.

    Definida como ``def`` normal (no ``async def``) a proposito: FastAPI
    corre las rutas sincronicas en un thread aparte automaticamente, asi
    que las llamadas que bloquean (a Claude, a Telegram, al grafo) no
    frenan al servidor entero mientras esperan respuesta.
    """
    mensaje = actualizacion.get("message")
    if mensaje is None:
        # Telegram manda otros tipos de "update" (ediciones, reacciones,
        # etc.) que no nos interesan -- se ignoran sin hacer nada.
        return {"ok": True}

    chat_id = mensaje["chat"]["id"]

    if not _autorizado(chat_id, x_telegram_bot_api_secret_token):
        return {"ok": True}

    ruta_imagen = _bajar_imagen_si_hay(mensaje)
    transcripcion = _transcribir_audio_si_hay(mensaje)

    # Que texto entra al grafo, por orden de prioridad:
    #   1. lo que se dijo en un audio, ya transcripto (Fase 7.5)
    #   2. el texto tipeado
    #   3. el pie de una foto (va en "caption", no en "text")
    texto = transcripcion or mensaje.get("text") or mensaje.get("caption") or ""

    grafo = request.app.state.grafo
    config = {"configurable": {"thread_id": str(chat_id)}}

    if grafo.get_state(config).next:
        # Hay una ejecucion pausada esperando esta respuesta (Fase 5:
        # "/probar_confirmacion" dejo el grafo en pausa la vez anterior).
        resultado = grafo.invoke(Command(resume=texto), config=config)
    else:
        resultado = grafo.invoke(
            Estado(mensaje_usuario=texto, ruta_imagen=ruta_imagen), config=config
        )

    if "__interrupt__" in resultado:
        pregunta = resultado["__interrupt__"][0].value
        enviar_mensaje(chat_id, str(pregunta))
    else:
        enviar_mensaje(chat_id, str(resultado["respuesta_final"]))

    return {"ok": True}
