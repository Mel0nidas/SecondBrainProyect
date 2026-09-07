"""Almacen de recordatorios (Fase 10 -- proactividad).

Un recordatorio es una linea en ``90-sistema/recordatorios.jsonl`` dentro
de la boveda. Se guarda ahi (y no en una base de datos aparte) por lo
mismo que ``correcciones.jsonl``: viaja a la PC de Melo por Syncthing, se
lee y se edita desde Obsidian, y no suma infra.

Las horas se guardan SIEMPRE en UTC (ISO con offset). La conversion
desde/hacia la hora local del usuario la hace el nodo del grafo.

Escrituras: el alta es un ``append`` (atomico para lineas cortas); los
cambios de estado reescriben el archivo entero via ``os.replace`` (chico,
un puñado de lineas). Un choque entre el loop del scheduler y el webhook
es posible pero improbable a este volumen.
"""

import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from mcp_obsidian.operaciones import ruta_boveda

RUTA_RELATIVA = "90-sistema/recordatorios.jsonl"

ESTADO_PENDIENTE = "pendiente"
ESTADO_ENVIADO = "enviado"
ESTADO_CANCELADO = "cancelado"


@dataclass
class Recordatorio:
    id: str
    texto: str
    cuando: str  # ISO UTC, ej "2026-09-09T13:00:00+00:00"
    chat_id: int
    creado: str  # ISO UTC
    estado: str

    def cuando_dt(self) -> datetime:
        return datetime.fromisoformat(self.cuando)


def _ruta() -> Path:
    return ruta_boveda() / RUTA_RELATIVA


def _leer_todos() -> list[Recordatorio]:
    ruta = _ruta()
    if not ruta.exists():
        return []
    recordatorios: list[Recordatorio] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        limpia = linea.strip()
        if not limpia:
            continue
        recordatorios.append(Recordatorio(**json.loads(limpia)))
    return recordatorios


def _reescribir(recordatorios: list[Recordatorio]) -> None:
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".jsonl.tmp")
    contenido = "".join(
        json.dumps(asdict(r), ensure_ascii=False) + "\n" for r in recordatorios
    )
    tmp.write_text(contenido, encoding="utf-8")
    os.replace(tmp, ruta)


def agregar(texto: str, cuando_utc: datetime, chat_id: int, ahora_utc: datetime) -> Recordatorio:
    """Da de alta un recordatorio pendiente y devuelve el registro creado."""
    recordatorio = Recordatorio(
        id=secrets.token_hex(3),
        texto=texto,
        cuando=cuando_utc.isoformat(),
        chat_id=chat_id,
        creado=ahora_utc.isoformat(),
        estado=ESTADO_PENDIENTE,
    )
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("a", encoding="utf-8") as salida:
        salida.write(json.dumps(asdict(recordatorio), ensure_ascii=False) + "\n")
    return recordatorio


def pendientes() -> list[Recordatorio]:
    return [r for r in _leer_todos() if r.estado == ESTADO_PENDIENTE]


def vencidos(ahora_utc: datetime) -> list[Recordatorio]:
    """Pendientes cuya hora ya llego."""
    return [r for r in pendientes() if r.cuando_dt() <= ahora_utc]


def _cambiar_estado(id_: str, nuevo: str) -> bool:
    todos = _leer_todos()
    encontrado = False
    for r in todos:
        if r.id == id_ and r.estado == ESTADO_PENDIENTE:
            r.estado = nuevo
            encontrado = True
    if encontrado:
        _reescribir(todos)
    return encontrado


def marcar_enviado(id_: str) -> bool:
    return _cambiar_estado(id_, ESTADO_ENVIADO)


def marcar_cancelado(id_: str) -> bool:
    return _cambiar_estado(id_, ESTADO_CANCELADO)
