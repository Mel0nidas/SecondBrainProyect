"""Estado del grafo de "hola mundo" de la Fase 1.

Este modelo es deliberadamente simple: solo existe para probar que el
grafo funciona de punta a punta. El estado real de produccion (con
intencion, snippets, presupuesto, etc.) se define en la Fase 2 -- ver
DISEÑO.md, PARTE 2.3.
"""

from pydantic import BaseModel


class EstadoSaludo(BaseModel):
    """Los datos que viajan entre los dos nodos del grafo de prueba.

    ``Pydantic`` es la libreria que valida esto: si en algun momento se
    intenta crear un ``EstadoSaludo`` sin ``mensaje_usuario``, o con un
    tipo de dato equivocado, explota en el momento (no mas adelante, con
    un error raro y dificil de rastrear).
    """

    mensaje_usuario: str
    respuesta: str | None = None
