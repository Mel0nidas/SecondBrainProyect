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

import asyncio
import calendar
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from fastapi import FastAPI, Header, Request
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from costos import registro as costos
from digestor.digestor import generar_digest
from grafo.estado import Estado, Intencion
from grafo.grafo import construir_grafo
from mcp_obsidian import operaciones
from rag.indexar import sincronizar_indice
from recordatorios import almacen
from telegram.cliente import descargar_archivo, enviar_mensaje
from transcripcion.groq import transcribir

logger = logging.getLogger(__name__)

# Cada cuanto el loop proactivo revisa recordatorios y el briefing.
INTERVALO_PROACTIVO_SEG = 60
# Cada cuanto se empareja el indice de busqueda con la boveda (notas que
# Melo edita en Obsidian, listas de tareas). Mas espaciado: es mas pesado.
INTERVALO_REINDEX_SEG = int(os.environ.get("INTERVALO_REINDEX_SEG", "300"))
# Hora local (0-23) a la que se manda el briefing matutino.
HORA_BRIEFING = int(os.environ.get("HORA_BRIEFING", "8"))
# Guarda la fecha del ultimo briefing mandado, para no repetirlo.
RUTA_ESTADO_BRIEFING = "90-sistema/ultimo_briefing.txt"
# Dia (0=lunes) y hora local del digest semanal, y su archivo de estado.
DIA_DIGEST = int(os.environ.get("DIA_DIGEST", "0"))
HORA_DIGEST = int(os.environ.get("HORA_DIGEST", "9"))
RUTA_ESTADO_DIGEST = "90-sistema/ultimo_digest.txt"

# Se llama ACA, al importar el modulo -- es decir, apenas arranca
# uvicorn, antes de que se procese ningun pedido. Si se llamara mas
# tarde (por ejemplo dentro de una funcion), podria ser demasiado
# tarde para variables que se leen durante el arranque del servidor,
# como la ruta del checkpointer de SQLite.
load_dotenv()


def _ruta_checkpoints() -> str:
    return os.environ.get("RUTA_CHECKPOINTS_SQLITE", "grafo_checkpoints.sqlite")


def _tz_usuario() -> ZoneInfo:
    return ZoneInfo(os.environ.get("TZ_USUARIO", "America/Argentina/Buenos_Aires"))


def _sumar_meses(dt: datetime, meses: int) -> datetime:
    """dt + N meses, recortando el dia si el mes destino es mas corto."""
    indice = dt.month - 1 + meses
    anio = dt.year + indice // 12
    mes = indice % 12 + 1
    dia = min(dt.day, calendar.monthrange(anio, mes)[1])
    return dt.replace(year=anio, month=mes, day=dia)


def _proxima_ocurrencia(cuando: datetime, repetir: str, ahora: datetime) -> datetime:
    """La siguiente vez que toca un recordatorio recurrente, ya en el futuro.

    Si el loop estuvo caido varios dias, avanza tantas veces como haga falta.
    """
    siguiente = cuando
    while siguiente <= ahora:
        if repetir == "diario":
            siguiente += timedelta(days=1)
        elif repetir == "semanal":
            siguiente += timedelta(weeks=1)
        elif repetir == "mensual":
            siguiente = _sumar_meses(siguiente, 1)
        else:
            return siguiente
    return siguiente


def _disparar_recordatorios_vencidos(ahora_utc: datetime | None = None) -> int:
    """Manda por Telegram los recordatorios cuya hora ya llego.

    Devuelve cuantos disparo. Los de una sola vez se marcan ``enviado``;
    los recurrentes se reprograman a la proxima ocurrencia. El cambio se
    hace DESPUES de mandar: si el envio falla, queda pendiente y se
    reintenta en el proximo tick.
    """
    ahora = ahora_utc or datetime.now(UTC)
    disparados = 0
    for r in almacen.vencidos(ahora):
        enviar_mensaje(r.chat_id, f"⏰ Recordatorio: {r.texto}")
        if r.repetir != "no":
            almacen.reprogramar(r.id, _proxima_ocurrencia(r.cuando_dt(), r.repetir, ahora))
        else:
            almacen.marcar_enviado(r.id)
        disparados += 1
    return disparados


def _armar_briefing(ahora_local: datetime) -> str | None:
    """El texto del briefing matutino, o None si no hay nada que decir."""
    tz = _tz_usuario()
    hoy = ahora_local.date()

    de_hoy = sorted(
        (r for r in almacen.pendientes() if r.cuando_dt().astimezone(tz).date() == hoy),
        key=lambda r: r.cuando,
    )
    listas = [
        (nombre, len(items))
        for nombre in operaciones.listar_listas()
        if (items := operaciones.leer_lista(nombre))
    ]
    if not de_hoy and not listas:
        return None

    partes = [f"Buen dia. Hoy es {ahora_local.strftime('%d/%m')}."]
    if de_hoy:
        partes.append("\nHoy:")
        for r in de_hoy:
            partes.append(f"  {r.cuando_dt().astimezone(tz).strftime('%H:%M')}  {r.texto}")
    if listas:
        partes.append("\nListas abiertas: " + ", ".join(f"{n} ({c})" for n, c in listas))
    return "\n".join(partes)


def _enviar_briefing_si_toca(ahora_local: datetime | None = None) -> bool:
    """Manda el briefing una vez por dia, a partir de HORA_BRIEFING.

    Usa un archivo con la fecha del ultimo envio para no repetirlo aunque
    el loop pase muchas veces dentro de la ventana horaria.
    """
    ahora = ahora_local or datetime.now(_tz_usuario())
    if ahora.hour < HORA_BRIEFING:
        return False

    estado = operaciones.ruta_boveda() / RUTA_ESTADO_BRIEFING
    hoy = ahora.date().isoformat()
    if estado.exists() and estado.read_text(encoding="utf-8").strip() == hoy:
        return False

    texto = _armar_briefing(ahora)
    estado.parent.mkdir(parents=True, exist_ok=True)
    estado.write_text(hoy, encoding="utf-8")  # se marca aunque no haya nada, para no re-chequear
    if texto is None:
        return False

    enviar_mensaje(int(os.environ["TELEGRAM_CHAT_ID_AUTORIZADO"]), texto)
    return True


def _enviar_digest_si_toca(ahora_local: datetime | None = None) -> bool:
    """Manda el digest semanal una vez por semana, el dia DIA_DIGEST a
    partir de HORA_DIGEST. Dedup por semana ISO en un archivo de estado."""
    ahora = ahora_local or datetime.now(_tz_usuario())
    if ahora.weekday() != DIA_DIGEST or ahora.hour < HORA_DIGEST:
        return False

    estado = operaciones.ruta_boveda() / RUTA_ESTADO_DIGEST
    semana = ahora.strftime("%G-W%V")
    if estado.exists() and estado.read_text(encoding="utf-8").strip() == semana:
        return False

    estado.parent.mkdir(parents=True, exist_ok=True)
    estado.write_text(semana, encoding="utf-8")

    texto = generar_digest(ahora)
    if texto is None:
        return False
    enviar_mensaje(int(os.environ["TELEGRAM_CHAT_ID_AUTORIZADO"]), texto)
    return True


async def _loop_proactivo() -> None:
    """Tarea de fondo: recordatorios vencidos + briefing matutino + digest
    semanal, cada minuto.

    Corre en el mismo proceso que el webhook (no hace falta EventBridge ni
    un cron aparte). Una excepcion nunca corta el loop.
    """
    while True:
        try:
            n = await asyncio.to_thread(_disparar_recordatorios_vencidos)
            if n:
                logger.info("Recordatorios disparados: %d", n)
            if await asyncio.to_thread(_enviar_briefing_si_toca):
                logger.info("Briefing matutino enviado")
            if await asyncio.to_thread(_enviar_digest_si_toca):
                logger.info("Digest semanal enviado")
        except Exception:
            logger.exception("Fallo el loop proactivo; sigo en el proximo tick")
        await asyncio.sleep(INTERVALO_PROACTIVO_SEG)


async def _loop_reindexado() -> None:
    """Tarea de fondo: empareja el indice de busqueda con la boveda.

    Reindexa lo que Melo edito en Obsidian y las listas de tareas, que
    nunca pasan por el Archivista. Una excepcion nunca corta el loop.
    """
    while True:
        try:
            resumen = await asyncio.to_thread(sincronizar_indice)
            if resumen["actualizadas"] or resumen["borradas"]:
                logger.info("Indice sincronizado: %s", resumen)
        except Exception:
            logger.exception("Fallo la sincronizacion del indice; sigo en el proximo tick")
        await asyncio.sleep(INTERVALO_REINDEX_SEG)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Arma el grafo UNA sola vez, cuando arranca el servidor, y lanza las
    tareas de fondo (recordatorios y sincronizacion del indice).

    El checkpointer de SQLite es lo que permite que ``interrupt()``
    pause una ejecucion y la retome en un pedido HTTP completamente
    distinto (quizas minutos despues, o incluso si el servidor se
    reinicio en el medio) -- sin el, cada mensaje de Telegram arrancaria
    de cero, sin memoria del anterior.
    """
    with SqliteSaver.from_conn_string(_ruta_checkpoints()) as checkpointer:
        app.state.grafo = construir_grafo(checkpointer=checkpointer)
        tareas_fondo = [
            asyncio.create_task(_loop_proactivo()),
            asyncio.create_task(_loop_reindexado()),
        ]
        try:
            yield
        finally:
            for tarea in tareas_fondo:
                tarea.cancel()


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


# /corregir: solo estas intenciones producen una nota que tenga sentido
# re-archivar. Para el resto (consultar, comando, ambiguo) el comando solo
# registra el caso para el set de evaluacion, sin mover nada.
CARPETA_POR_INTENCION = {
    Intencion.CAPTURAR: operaciones.CARPETA_INBOX,
    Intencion.TAREA: operaciones.CARPETA_TAREAS,
    Intencion.IMAGEN: operaciones.CARPETA_IMAGENES,
}

RUTA_CORRECCIONES = "90-sistema/correcciones.jsonl"


def _registrar_correccion(mensaje: str, intencion: Intencion) -> None:
    """Agrega el caso corregido al log de la boveda (DISEÑO.md §6).

    El contenedor tiene ``src/`` pero no ``tests/``, asi que no puede
    escribir ``tests/eval/mensajes.jsonl`` directo. Escribe en la boveda,
    que Syncthing lleva a la PC de Melo; alla ``tests/eval/incorporar.py``
    lo mergea al set y Melo lo commitea.
    """
    archivo = operaciones.ruta_boveda() / RUTA_CORRECCIONES
    archivo.parent.mkdir(parents=True, exist_ok=True)
    linea = json.dumps(
        {"mensaje": mensaje, "intencion": intencion.value, "fuente": "real"},
        ensure_ascii=False,
    )
    with archivo.open("a", encoding="utf-8") as salida:
        salida.write(linea + "\n")


def _manejar_corregir(texto: str, grafo: Any, config: dict[str, Any]) -> str | None:
    """Procesa ``/corregir <intencion>``.

    Devuelve el texto de respuesta para Telegram, o ``None`` si el mensaje
    no era un ``/corregir`` (para que siga el flujo normal del grafo).

    Actua sobre el resultado de la corrida ANTERIOR, leyendo su estado del
    checkpointer -- por eso se resuelve aca, en el webhook, antes de volver
    a invocar el grafo.
    """
    partes = texto.strip().split()
    if not partes or partes[0] != "/corregir":
        return None

    validas = ", ".join(i.value for i in Intencion)
    if len(partes) < 2:
        return f"Uso: /corregir <intencion>. Opciones: {validas}."
    try:
        nueva = Intencion(partes[1].lower())
    except ValueError:
        return f'"{partes[1]}" no es una intencion valida. Opciones: {validas}.'

    previo = grafo.get_state(config).values
    if not isinstance(previo, dict):
        previo = dict(previo) if previo else {}

    mensaje_previo = previo.get("mensaje_usuario")
    if not mensaje_previo:
        return "No hay nada que corregir todavia."

    cruda = previo.get("intencion")
    intencion_previa = Intencion(cruda) if cruda else None
    if intencion_previa == nueva:
        return f'El ultimo mensaje ya quedo como "{nueva.value}". No cambie nada.'

    _registrar_correccion(str(mensaje_previo), nueva)

    ruta_nota = previo.get("ruta_nota_creada")
    destino = CARPETA_POR_INTENCION.get(nueva)
    movida = ""
    if ruta_nota and destino and not str(ruta_nota).startswith(f"{destino}/"):
        resultado = operaciones.mover_nota(str(ruta_nota), destino)
        movida = (
            f" La nota se movio a {resultado}."
            if resultado.startswith(f"{destino}/")
            else f" ({resultado})"
        )

    antes = f' (era "{intencion_previa.value}")' if intencion_previa else ""
    return f'Corregido a "{nueva.value}"{antes} y anotado para la evaluacion.{movida}'


def _manejar_recordatorios(texto: str) -> str | None:
    """Procesa ``/recordatorios`` (lista los pendientes) y ``/cancelar <id>``.

    Devuelve el texto de respuesta, o ``None`` si el mensaje no era uno de
    esos comandos.
    """
    limpio = texto.strip()

    if limpio == "/recordatorios":
        pend = sorted(almacen.pendientes(), key=lambda r: r.cuando)
        if not pend:
            return "No tenes recordatorios pendientes."
        tz = _tz_usuario()
        cada = {"diario": " (cada dia)", "semanal": " (cada semana)", "mensual": " (cada mes)"}
        lineas = [
            f"- {r.cuando_dt().astimezone(tz).strftime('%d/%m %H:%M')}  {r.texto}"
            f"{cada.get(r.repetir, '')}   /cancelar {r.id}"
            for r in pend
        ]
        return "Recordatorios pendientes:\n" + "\n".join(lineas)

    if limpio.startswith("/cancelar "):
        id_ = limpio.split(maxsplit=1)[1].strip()
        if almacen.marcar_cancelado(id_):
            return "Recordatorio cancelado."
        return f"No encontre un recordatorio pendiente con id {id_}."

    return None


def _manejar_lista(texto: str) -> str | None:
    """Procesa ``/lista`` (nombra las listas) y ``/lista <nombre>`` (la muestra)."""
    limpio = texto.strip()

    if limpio == "/lista":
        nombres = operaciones.listar_listas()
        if not nombres:
            return (
                "Todavia no tenes ninguna lista. Deci algo como "
                '"compra pan la proxima vez que vayas al super".'
            )
        return "Tus listas: " + ", ".join(nombres) + ".\nMira una con /lista <nombre>."

    if limpio.startswith("/lista "):
        nombre = limpio.split(maxsplit=1)[1].strip()
        items = operaciones.leer_lista(nombre)
        if not items:
            return f'La lista "{nombre}" esta vacia o no existe.'
        return f"Lista {nombre}:\n" + "\n".join(f"• {i}" for i in items)

    if limpio == "/reindexar":
        r = sincronizar_indice()
        return (
            f"Indice al dia: {r['actualizadas']} nota(s) reindexada(s), "
            f"{r['borradas']} borrada(s)."
        )

    if limpio == "/digest":
        return generar_digest(datetime.now(_tz_usuario())) or (
            "No hay nada para el repaso: ni notas de la semana, ni listas abiertas."
        )

    if limpio == "/costos":
        return costos.resumen()

    return None


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
    pausado = bool(grafo.get_state(config).next)

    if not pausado:
        # Comandos operativos que no pasan por el grafo: "/corregir" actua
        # sobre la corrida anterior (DISEÑO.md §6), "/recordatorios" y
        # "/cancelar" leen/escriben el almacen de recordatorios.
        respuesta_op = _manejar_corregir(texto, grafo, config)
        if respuesta_op is None:
            respuesta_op = _manejar_recordatorios(texto)
        if respuesta_op is None:
            respuesta_op = _manejar_lista(texto)
        if respuesta_op is not None:
            enviar_mensaje(chat_id, respuesta_op)
            return {"ok": True}

    if pausado:
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
