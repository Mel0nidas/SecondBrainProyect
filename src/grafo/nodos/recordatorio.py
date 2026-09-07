"""Nodo Recordatorio (Fase 10 -- proactividad).

A diferencia de una "tarea" (que solo se guarda en una lista), un
recordatorio hace que el bot te ESCRIBA solo cuando llega la hora. El
chequeo de vencimientos lo hace un loop en ``app/main.py``; este nodo
solo interpreta el "cuando" del mensaje y da de alta el registro en
``recordatorios.almacen``.
"""

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from langchain_anthropic import ChatAnthropic

from costos import registro as costos
from grafo.estado import Estado, RecordatorioPropuesta
from grafo.utilidades import cargar_prompt
from recordatorios import almacen

MODELO_RECORDATORIO = "claude-sonnet-5"

_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def _tz() -> ZoneInfo:
    # Buenos Aires no tiene horario de verano hoy, asi que attach por
    # ``replace`` alcanza. Si se soporta otra zona con DST, revisar esto.
    return ZoneInfo(os.environ.get("TZ_USUARIO", "America/Argentina/Buenos_Aires"))


def _chat_id() -> int:
    # Asistente de un solo usuario: el unico chat es el autorizado.
    return int(os.environ["TELEGRAM_CHAT_ID_AUTORIZADO"])


def _formato_local(dt: datetime) -> str:
    return f"{_DIAS[dt.weekday()]} {dt.day:02d}/{dt.month:02d} {dt.hour:02d}:{dt.minute:02d}"


def recordatorio(estado: Estado) -> dict[str, object]:
    ahora_local = datetime.now(_tz())

    modelo = ChatAnthropic(model=MODELO_RECORDATORIO)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(RecordatorioPropuesta, include_raw=True)

    prompt = cargar_prompt("recordatorio")
    contexto = (
        f"Ahora es {ahora_local.strftime('%Y-%m-%dT%H:%M:%S')} "
        f"({_DIAS[ahora_local.weekday()]}).\n\n"
        f"Mensaje del usuario: {estado.mensaje_usuario}"
    )
    propuesta = costos.extraer(
        modelo_estructurado.invoke(f"{prompt}\n\n{contexto}"), MODELO_RECORDATORIO, "recordatorio"
    )
    assert isinstance(propuesta, RecordatorioPropuesta)

    if not propuesta.entendido or not propuesta.cuando.strip():
        return {
            "respuesta_final": (
                "¿Para cuándo querés que te lo recuerde? Decime una hora o fecha "
                '(ej: "mañana 9am", "el martes", "en 2 horas").'
            )
        }

    try:
        cuando_local = datetime.fromisoformat(propuesta.cuando).replace(tzinfo=_tz())
    except ValueError:
        return {"respuesta_final": "No entendi la fecha. Probá de nuevo con otra forma."}

    ahora_utc = datetime.now(UTC)
    cuando_utc = cuando_local.astimezone(UTC)
    if cuando_utc <= ahora_utc:
        return {"respuesta_final": "Esa hora ya paso. Decime un momento futuro."}

    repetir = propuesta.repetir if propuesta.repetir in almacen.REPETIR_VALIDOS else "no"
    almacen.agregar(propuesta.texto, cuando_utc, _chat_id(), ahora_utc, repetir=repetir)

    cuando_txt = _formato_local(cuando_local)
    cada = {"diario": " y cada día", "semanal": " y cada semana", "mensual": " y cada mes"}
    return {
        "respuesta_final": (
            f'Listo. Te recuerdo "{propuesta.texto}" el {cuando_txt}{cada.get(repetir, "")}.'
        )
    }
