"""Nodo Archivista (DISEÑO.md §2.2): escribe notas en la boveda.

Desde la Fase 3, escribe en la boveda REAL de Obsidian, a traves del
cliente MCP (no toca archivos directamente -- eso ahora es trabajo del
servidor MCP, ver ``mcp_obsidian/servidor.py``).

Desde la Fase 4, ademas dispara la indexacion semantica de la nota
recien creada (ver ``rag/indexar.py``), para que el Bibliotecario pueda
encontrarla despues aunque la pregunta use otras palabras.

Desde la Fase 7 tiene dos ramas: texto (la de siempre) e imagen. La de
imagen le manda la foto a Claude con vision y arma una nota con la
transcripcion del texto visible (DISEÑO.md §2.6).
"""

import base64
import mimetypes

from langchain_anthropic import ChatAnthropic

from grafo.estado import Estado, NotaImagenPropuesta, NotaPropuesta
from grafo.utilidades import cargar_prompt
from mcp_obsidian import operaciones
from mcp_obsidian.cliente import llamar_herramienta
from rag.indexar import indexar_nota

MODELO_ARCHIVISTA = "claude-sonnet-4-6"


def archivista(estado: Estado) -> dict[str, object]:
    if estado.ruta_imagen is not None:
        return _archivar_imagen(estado, estado.ruta_imagen)
    return _archivar_texto(estado)


def _archivar_texto(estado: Estado) -> dict[str, object]:
    modelo = ChatAnthropic(model=MODELO_ARCHIVISTA)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(NotaPropuesta)

    prompt = cargar_prompt("archivista")
    entrada = f"{prompt}\n\nMensaje del usuario: {estado.mensaje_usuario}"
    propuesta = modelo_estructurado.invoke(entrada)
    assert isinstance(propuesta, NotaPropuesta)

    resultado = llamar_herramienta(
        "crear_nota",
        titulo=propuesta.titulo,
        tags=propuesta.tags,
        contenido=estado.mensaje_usuario,
    )
    ruta = resultado[0]

    # Indexacion incremental: solo esta nota, no toda la boveda de nuevo.
    indexar_nota(
        ruta=ruta, titulo=propuesta.titulo, tags=propuesta.tags, contenido=estado.mensaje_usuario
    )

    return {"respuesta_final": f'Guardado como "{propuesta.titulo}" ({ruta}).'}


def _archivar_imagen(estado: Estado, ruta_imagen: str) -> dict[str, object]:
    """Manda la foto a Claude con vision y arma la nota que la acompaña.

    La imagen ya fue bajada de Telegram y guardada en la boveda por el
    webhook -- aca solo se la lee del disco para mandarsela al modelo.
    """
    propuesta = _describir_imagen(estado, ruta_imagen)
    cuerpo = _armar_cuerpo(propuesta, ruta_imagen, estado.mensaje_usuario)

    resultado = llamar_herramienta(
        "crear_nota",
        titulo=propuesta.titulo,
        tags=propuesta.tags,
        contenido=cuerpo,
        carpeta=operaciones.CARPETA_IMAGENES,
        origen="telegram-imagen",
    )
    ruta_nota = resultado[0]

    # Se indexa la NOTA (su transcripcion y descripcion), no la imagen:
    # el buscador trabaja sobre texto, asi que la foto se vuelve
    # encontrable a traves de lo que el modelo leyo en ella.
    indexar_nota(ruta=ruta_nota, titulo=propuesta.titulo, tags=propuesta.tags, contenido=cuerpo)

    return {"respuesta_final": f'Guardada la foto como "{propuesta.titulo}" ({ruta_nota}).'}


def _describir_imagen(estado: Estado, ruta_imagen: str) -> NotaImagenPropuesta:
    datos = (operaciones.ruta_boveda() / ruta_imagen).read_bytes()
    tipo_mime = mimetypes.guess_type(ruta_imagen)[0] or "image/jpeg"

    modelo = ChatAnthropic(model=MODELO_ARCHIVISTA)  # type: ignore[call-arg]
    modelo_estructurado = modelo.with_structured_output(NotaImagenPropuesta)

    prompt = cargar_prompt("archivista_imagen")
    if estado.mensaje_usuario.strip():
        prompt = f"{prompt}\n\nTexto que el usuario mandó con la foto: {estado.mensaje_usuario}"

    # El bloque de imagen va en el mismo mensaje que el prompt. El
    # formato ({"type": "image", "base64": ..., "mime_type": ...}) es el
    # estandar de LangChain, que la libreria traduce al de Anthropic.
    mensaje = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "base64": base64.b64encode(datos).decode("ascii"),
                    "mime_type": tipo_mime,
                },
            ],
        }
    ]
    propuesta = modelo_estructurado.invoke(mensaje)
    assert isinstance(propuesta, NotaImagenPropuesta)
    return propuesta


def _armar_cuerpo(propuesta: NotaImagenPropuesta, ruta_imagen: str, mensaje_usuario: str) -> str:
    """Arma el markdown de la nota, con el link a la foto original.

    El link usa la sintaxis ``![[archivo]]`` de Obsidian, que muestra la
    imagen embebida al abrir la nota.
    """
    nombre_archivo = ruta_imagen.split("/")[-1]
    partes = [f"![[{nombre_archivo}]]", "", propuesta.descripcion]

    if mensaje_usuario.strip():
        partes += ["", f"> {mensaje_usuario.strip()}"]

    if propuesta.transcripcion.strip():
        partes += ["", "## Transcripción", "", propuesta.transcripcion.strip()]

    return "\n".join(partes)
