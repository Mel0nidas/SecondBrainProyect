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
        "/costos - resumen de costos (todavia no implementado de verdad)\n"
        "/corregir <intencion> - si clasifique mal el ultimo mensaje, lo\n"
        "  re-archiva y lo anota para la evaluacion. Ej: /corregir tarea\n"
        "/recordatorios - lista los recordatorios pendientes\n"
        "/cancelar <id> - cancela un recordatorio\n"
        "/lista - nombra tus listas; /lista <nombre> - la muestra\n"
        "/reindexar - fuerza la indexacion de lo que editaste en Obsidian\n"
        "/digest - el repaso semanal, ahora mismo\n"
        "\n"
        "Escribi normal para: agendar un aviso, tambien recurrente\n"
        '  ("recordame X el martes", "todos los lunes recordame Y");\n'
        'sumar a una lista ("compra pan la proxima vez que vayas al super").\n'
        "Todas las mananas te mando lo que vence hoy + tus listas abiertas,\n"
        "y una vez por semana un repaso de lo que capturaste."
    ),
    "/estado": (
        "Corriendo en produccion (AWS, 24/7). Entiende texto, fotos y notas "
        "de voz por Telegram; guarda notas, maneja listas de tareas, responde "
        "consultas con busqueda semantica, agenda recordatorios (incluso "
        "recurrentes), y manda un briefing cada manana y un repaso cada semana."
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
