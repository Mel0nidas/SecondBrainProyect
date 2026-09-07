"""Transcripción de audio con Groq (DISEÑO.md §FASE 7.5).

La API de Claude no acepta audio: lo ignora y lo descarta. Así que un
audio que llega por Telegram necesita un paso previo que lo convierta a
texto antes de entrar al grafo. Ese paso lo hace Groq, que corre el
modelo Whisper (de OpenAI, pero servido por Groq) muy rápido y con un
tier gratuito que a nuestro volumen sale $0 (ver DISEÑO.md §4.4).

Una vez transcripto, el texto entra al grafo como si el usuario lo
hubiera tipeado: el Router y el Archivista de siempre lo manejan sin
cambios.

Se habla con la API por HTTP directo (como ``telegram/cliente.py``), sin
SDK: es un solo endpoint y evita sumar una dependencia. El endpoint es
compatible con el de OpenAI, de ahí el ``/openai/`` en la URL.
"""

import os

import httpx

# Whisper "turbo": la variante rápida y barata, suficiente para notas de
# voz cortas. Nombre vigente al construir la Fase 7.5.
MODELO_TRANSCRIPCION = "whisper-large-v3-turbo"
URL_TRANSCRIPCION = "https://api.groq.com/openai/v1/audio/transcriptions"

# Transcribir tarda más que una llamada HTTP normal, sobre todo si el
# audio es largo -- se le da margen holgado.
TIMEOUT_SEGUNDOS = 120.0


def transcribir(datos: bytes, nombre_archivo: str = "audio.ogg") -> str:
    """Manda los bytes de un audio a Groq y devuelve el texto transcripto.

    ``nombre_archivo`` sólo se usa para que Groq reconozca el formato por
    la extensión (Telegram manda las notas de voz en OGG/Opus, que
    Whisper acepta sin transcodificar). El contenido real son los
    ``datos``.

    Se fuerza ``language="es"``: el usuario habla español, y decírselo de
    antemano evita que Whisper se confunda de idioma en clips cortos.
    """
    clave = os.environ.get("GROQ_API_KEY")
    if not clave:
        raise RuntimeError("Falta la variable de entorno GROQ_API_KEY.")

    respuesta = httpx.post(
        URL_TRANSCRIPCION,
        headers={"Authorization": f"Bearer {clave}"},
        files={"file": (nombre_archivo, datos, "application/octet-stream")},
        data={"model": MODELO_TRANSCRIPCION, "language": "es"},
        timeout=TIMEOUT_SEGUNDOS,
    )
    respuesta.raise_for_status()
    return str(respuesta.json()["text"]).strip()
