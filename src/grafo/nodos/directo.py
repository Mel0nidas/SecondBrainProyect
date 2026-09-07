"""Nodo de respuesta directa (DISEÑO.md §2.2): comandos fijos, sin LLM.

Ademas de los comandos reales (/ayuda, /estado), este nodo tiene DOS
comandos de prueba que no hacen nada util a proposito -- existen solo
para probar mecanismos del grafo de punta a punta:

- "/test_loop": prueba el corte por presupuesto (Fase 2).
- "/probar_confirmacion": prueba la pausa human-in-the-loop (Fase 5).
  Hoy el Archivista no tiene ninguna accion realmente destructiva (no
  puede borrar ni sobrescribir), asi que no hay nada real que pausar
  todavia -- pero el mecanismo de "pausar y esperar confirmacion por
  Telegram" queda armado y probado, listo para cuando haga falta.
"""

from langgraph.types import interrupt

from grafo.estado import Estado

RESPUESTAS_FIJAS = {
    "/ayuda": (
        "Comandos disponibles:\n"
        "/ayuda - muestra este mensaje\n"
        "/estado - en que fase esta el proyecto\n"
        "/costos - resumen de costos (todavia no implementado de verdad)"
    ),
    "/estado": (
        "Corriendo en produccion (AWS, 24/7). Ultima fase entregada: 7.5. "
        "Entiende texto, fotos y notas de voz por Telegram; consultas con "
        "busqueda semantica."
    ),
    "/costos": "Todavia no se trackea el costo real -- llega mas adelante en el plan.",
}


def directo(estado: Estado) -> dict[str, object]:
    mensaje = estado.mensaje_usuario.strip()

    if mensaje == "/test_loop":
        # A proposito no hace nada util: sirve para probar que el corte
        # por presupuesto funciona. La arista condicional del grafo lo
        # vuelve a mandar a este mismo nodo mientras no se haya cortado.
        return {}

    if mensaje == "/probar_confirmacion":
        # ``interrupt()`` pausa el grafo aca mismo: la ejecucion corta,
        # el pedido HTTP del webhook devuelve la pregunta, y el grafo
        # queda guardado (gracias al checkpointer de SQLite) esperando
        # la respuesta -- que llega como un mensaje de Telegram nuevo,
        # en un pedido HTTP totalmente distinto, quizas minutos despues.
        respuesta = interrupt("Esto es una PRUEBA, no hace nada real. ¿Confirmas? (si/no)")
        if str(respuesta).strip().lower() in ("si", "sí", "yes", "y"):
            return {"respuesta_final": "Accion de prueba CONFIRMADA. (No paso nada real.)"}
        return {"respuesta_final": "Accion de prueba CANCELADA."}

    if mensaje in RESPUESTAS_FIJAS:
        return {"respuesta_final": RESPUESTAS_FIJAS[mensaje]}

    return {"respuesta_final": "No entendi bien que necesitas. ¿Podes reformular el mensaje?"}
