"""Digestor semanal (Fase 14 -- el agente diferido de DISEÑO.md §2.2).

No responde a mensajes: lo dispara el loop proactivo de ``app/main.py``
una vez por semana. Recorre la boveda y arma un repaso:

- qué se capturó en los últimos 7 días (sintetizado por Claude);
- qué quedó juntando polvo en ``00-inbox/``;
- el estado de las listas de tareas.

Deja el repaso como nota en ``90-sistema/`` (queda en Obsidian) y
devuelve una version corta para mandar por Telegram.
"""

import re
from datetime import date, datetime, timedelta

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel

from costos import registro as costos
from grafo.utilidades import cargar_prompt, modelo_agentes
from mcp_obsidian import operaciones

MODELO_DIGESTOR = modelo_agentes()

DIAS_SEMANA = 7
DIAS_INBOX_VIEJO = 14
MAX_NOTAS_AL_MODELO = 25


class SintesisSemanal(BaseModel):
    temas: str
    sugerencia: str


def _fecha_de_nota(texto: str) -> date | None:
    m = re.search(r"^fecha:\s*(\d{4}-\d{2}-\d{2})\s*$", texto, flags=re.MULTILINE)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def _primeras_lineas(texto: str, n: int = 200) -> str:
    cuerpo = texto.split("---", 2)[-1]  # saltar frontmatter
    m = re.search(r"^# .+$", cuerpo, flags=re.MULTILINE)
    if m:
        cuerpo = cuerpo[m.end() :]
    return " ".join(cuerpo.split())[:n]


def _sintetizar(notas: list[tuple[str, str]]) -> SintesisSemanal:
    """notas = [(titulo, snippet), ...]. Una sola llamada al modelo."""
    listado = "\n".join(f"- {titulo}: {snippet}" for titulo, snippet in notas)
    prompt = cargar_prompt("digestor")
    modelo = ChatAnthropic(model=MODELO_DIGESTOR)  # type: ignore[call-arg]
    salida = costos.extraer(
        modelo.with_structured_output(SintesisSemanal, include_raw=True).invoke(
            f"{prompt}\n\nNotas de esta semana:\n{listado}"
        ),
        MODELO_DIGESTOR,
        "digestor",
    )
    assert isinstance(salida, SintesisSemanal)
    return salida


def generar_digest(ahora_local: datetime) -> str | None:
    """Arma el repaso semanal. Escribe la nota en 90-sistema/ y devuelve el
    texto corto para Telegram, o None si no hay nada que decir."""
    hoy = ahora_local.date()
    corte_semana = hoy - timedelta(days=DIAS_SEMANA)
    corte_viejo = hoy - timedelta(days=DIAS_INBOX_VIEJO)

    de_la_semana: list[tuple[str, str]] = []
    inbox_viejo: list[str] = []
    for rel in operaciones.listar_carpeta(""):
        # 20-tareas/ son listas (van aparte en el digest); 90-sistema/ son logs.
        if rel.startswith(("20-tareas/", "90-sistema/")):
            continue
        texto = operaciones.leer_nota(rel)
        fecha = _fecha_de_nota(texto)
        titulo = rel.rsplit("/", 1)[-1].removesuffix(".md")
        if fecha and fecha > corte_semana:
            de_la_semana.append((titulo, _primeras_lineas(texto)))
        if rel.startswith("00-inbox/") and fecha and fecha <= corte_viejo:
            inbox_viejo.append(titulo)

    listas = [
        (nombre, len(items))
        for nombre in operaciones.listar_listas()
        if (items := operaciones.leer_lista(nombre))
    ]

    if not de_la_semana and not inbox_viejo and not listas:
        return None

    partes = [f"Repaso semanal -- {hoy.isoformat()}", ""]
    if de_la_semana:
        sintesis = _sintetizar(de_la_semana[:MAX_NOTAS_AL_MODELO])
        partes += [
            f"Esta semana guardaste {len(de_la_semana)} nota(s).",
            "",
            sintesis.temas,
            "",
            f"Sugerencia: {sintesis.sugerencia}",
        ]
    else:
        partes.append("Esta semana no guardaste nada nuevo.")

    if inbox_viejo:
        partes += [
            "",
            f"En el inbox hace mas de {DIAS_INBOX_VIEJO} dias:",
            *(f"  - {t}" for t in inbox_viejo),
        ]
    if listas:
        partes += ["", "Listas abiertas: " + ", ".join(f"{n} ({c})" for n, c in listas)]

    texto = "\n".join(partes)

    operaciones.crear_nota(
        titulo=f"Repaso semanal {hoy.isoformat()}",
        tags=["digest"],
        contenido=texto,
        carpeta="90-sistema",
        origen="digestor",
    )
    return texto
