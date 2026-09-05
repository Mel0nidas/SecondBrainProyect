"""Estado real del grafo (Fase 2 en adelante).

Reemplaza el ``EstadoSaludo`` de la Fase 1. Sigue la forma general
descripta en DISEÑO.md, PARTE 2.3, aunque todavia mas simple: campos
como ``requiere_confirmacion`` o ``acciones_propuestas`` se agregan
recien cuando haya una accion destructiva real que los necesite
(Fase 5 en adelante).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class Intencion(StrEnum):
    """Las clases que puede devolver el Router.

    ``StrEnum`` (agregado en Python 3.11) se comporta como texto plano
    ademas de como enum: se puede comparar y guardar como si fuera un
    string, pero solo se puede crear con uno de estos seis valores.
    """

    CAPTURAR = "capturar"
    CONSULTAR = "consultar"
    TAREA = "tarea"
    IMAGEN = "imagen"
    COMANDO = "comando"
    AMBIGUO = "ambiguo"


class SalidaRouter(BaseModel):
    """Lo que le pedimos a Claude que devuelva en el nodo Router.

    Esto es lo que en LangChain se llama "salida estructurada": en vez
    de pedirle a Claude un texto libre y despues tratar de interpretarlo
    a mano, le pasamos este modelo y la libreria se encarga de que la
    respuesta encaje exactamente en esta forma (clase valida + numero).
    """

    clase: Intencion
    confianza: float


class NotaPropuesta(BaseModel):
    """Lo que le pedimos a Claude que decida al capturar una nota."""

    titulo: str
    tags: list[str]


class Presupuesto(BaseModel):
    """Limite de gasto de una corrida del grafo (DISEÑO.md §2.4.3).

    ``pasos_usados`` se incrementa una vez por cada paso del grafo. Si
    llega a ``pasos_maximos`` antes de terminar, el grafo corta la
    ejecucion y devuelve un resumen en vez de seguir gastando.
    """

    pasos_maximos: int = 15
    tokens_maximos: int = 50_000
    pasos_usados: int = 0
    tokens_usados: int = 0

    def excedido(self) -> bool:
        return self.pasos_usados >= self.pasos_maximos or self.tokens_usados >= self.tokens_maximos


class Estado(BaseModel):
    """El estado que viaja por todo el grafo, de nodo en nodo."""

    mensaje_usuario: str
    intencion: Intencion | None = None
    snippets: list[str] = Field(default_factory=list)
    respuesta_final: str | None = None
    presupuesto: Presupuesto = Field(default_factory=Presupuesto)
