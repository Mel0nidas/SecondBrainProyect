"""Nodo de respuesta directa (DISEÑO.md §2.2): comandos fijos, sin LLM.

Ademas de los comandos reales (/ayuda, /estado), este nodo tiene un
comando de prueba, "/test_loop", que existe UNICAMENTE para demostrar
y probar el mecanismo de corte por presupuesto: se llama a si mismo
sin parar, a proposito, hasta que ``verificar_presupuesto`` corta la
ejecucion. No es un comando real del asistente.
"""

from grafo.estado import Estado

RESPUESTAS_FIJAS = {
    "/ayuda": (
        "Comandos disponibles:\n"
        "/ayuda - muestra este mensaje\n"
        "/estado - en que fase esta el proyecto\n"
        "/costos - resumen de costos (todavia no implementado de verdad)"
    ),
    "/estado": "Fase 2: Router + esqueleto de agentes, corriendo local por CLI.",
    "/costos": "Todavia no se trackea el costo real -- llega mas adelante en el plan.",
}


def directo(estado: Estado) -> dict[str, object]:
    mensaje = estado.mensaje_usuario.strip()

    if mensaje == "/test_loop":
        # A proposito no hace nada util: sirve para probar que el corte
        # por presupuesto funciona. La arista condicional del grafo lo
        # vuelve a mandar a este mismo nodo mientras no se haya cortado.
        return {}

    if mensaje in RESPUESTAS_FIJAS:
        return {"respuesta_final": RESPUESTAS_FIJAS[mensaje]}

    if estado.intencion is not None and estado.intencion.value == "imagen":
        return {"respuesta_final": "Todavia no puedo procesar imagenes -- eso llega en la Fase 7."}

    return {"respuesta_final": "No entendi bien que necesitas. ¿Podes reformular el mensaje?"}
