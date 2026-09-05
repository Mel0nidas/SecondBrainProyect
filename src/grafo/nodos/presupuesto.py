"""Nodo contador de presupuesto (DISEÑO.md §2.4.3).

Este nodo no llama a Claude ni hace nada "inteligente": solo suma un
paso al contador. Corre antes de despachar a cualquier agente. La
funcion ``siguiente_paso`` (una "arista condicional") decide, mirando
el estado ya actualizado, si hay que seguir para adelante o cortar.
"""

from grafo.estado import Estado


def verificar_presupuesto(estado: Estado) -> dict[str, object]:
    presupuesto = estado.presupuesto.model_copy()
    presupuesto.pasos_usados += 1
    return {"presupuesto": presupuesto}


def resumen_parcial(estado: Estado) -> dict[str, object]:
    """Se ejecuta solo cuando el presupuesto se agoto sin terminar la tarea."""
    mensaje = (
        f"Corte por presupuesto: se alcanzaron {estado.presupuesto.pasos_usados} "
        f"pasos (limite: {estado.presupuesto.pasos_maximos}) sin completar la "
        "tarea. Esto es un corte de seguridad, no un error del sistema."
    )
    return {"respuesta_final": mensaje}
