"""Busqueda semantica sobre la boveda (DISEÑO.md §4.3, Fase 4).

Reemplaza (para el Bibliotecario) la busqueda por palabras clave de
``mcp_obsidian.operaciones.buscar_por_titulo`` por busqueda real por
significado:

1. Cada nota se corta en pedazos ("chunks") por seccion de markdown.
2. Cada chunk se convierte en un vector de numeros (un "embedding") con
   Voyage AI -- textos con significado parecido quedan con vectores
   parecidos, aunque no compartan palabras.
3. Los vectores se guardan en Chroma, una base de datos chica que vive
   en disco (no hace falta levantar ningun servidor aparte).
4. Para buscar, se calcula el embedding de la pregunta y se le pide a
   Chroma los chunks cuyo vector este mas cerca.

A diferencia del cliente MCP (que habla con un servidor en otro
proceso, ver ``mcp_obsidian/cliente.py``), esto se usa directo desde
los nodos del grafo: Chroma es una libreria embebida, no un servicio
externo que necesite ese aislamiento.
"""

import os
import re
from pathlib import Path
from typing import Literal

import chromadb
import voyageai

from mcp_obsidian import operaciones

NOMBRE_COLECCION = "notas"
MODELO_EMBEDDINGS = "voyage-3.5-lite"
CARACTERES_POR_TOKEN = 4  # aproximacion: no tenemos un contador exacto a mano


def ruta_indice() -> Path:
    """Lee la ruta del indice de Chroma desde el entorno en cada llamada.

    Mismo patron que ``mcp_obsidian.operaciones.ruta_boveda``: no se
    guarda en una constante de modulo, para que los tests puedan
    apuntar a una carpeta temporal distinta en cada caso.
    """
    valor = os.environ.get("RUTA_INDICE_CHROMA", "chroma_index")
    return Path(valor)


def _coleccion() -> chromadb.Collection:
    cliente = chromadb.PersistentClient(path=str(ruta_indice()))
    return cliente.get_or_create_collection(NOMBRE_COLECCION)


def _embeber(textos: list[str], tipo_entrada: Literal["document", "query"]) -> list[list[float]]:
    """Convierte texto en vectores usando Voyage AI.

    ``tipo_entrada`` distingue si estamos indexando notas ("document")
    o buscando ("query") -- Voyage entrena esos dos casos por separado
    y da mejores resultados si se lo decimos explicitamente.

    Aislada en su propia funcion a proposito: los tests la reemplazan
    (monkeypatch) por una version falsa, para no gastar llamadas reales
    a la API en cada corrida de ``pytest``.
    """
    cliente = voyageai.Client()  # type: ignore[attr-defined]  # lee VOYAGE_API_KEY del entorno
    resultado = cliente.embed(textos, model=MODELO_EMBEDDINGS, input_type=tipo_entrada)
    return [[float(numero) for numero in vector] for vector in resultado.embeddings]


def dividir_en_chunks(texto: str, tokens_max: int = 500) -> list[str]:
    """Corta el cuerpo de una nota en pedazos mas chicos para indexar.

    Primero corta por encabezados de markdown (lineas que empiezan con
    "#"), porque cada seccion suele ser una unidad de sentido propia.
    Si una seccion sola supera el limite de tokens, la vuelve a cortar
    por parrafos (lineas en blanco de por medio) hasta que cada pedazo
    entre en el limite.
    """
    limite_caracteres = tokens_max * CARACTERES_POR_TOKEN

    chunks: list[str] = []
    for seccion in _dividir_por_encabezados(texto):
        if len(seccion) <= limite_caracteres:
            chunks.append(seccion.strip())
        else:
            chunks.extend(_dividir_por_parrafos(seccion, limite_caracteres))

    return [c for c in chunks if c]


def _dividir_por_encabezados(texto: str) -> list[str]:
    partes = re.split(r"(?=^#{1,6}\s)", texto, flags=re.MULTILINE)
    return [p.strip() for p in partes if p.strip()]


def _dividir_por_parrafos(texto: str, limite_caracteres: int) -> list[str]:
    parrafos = [p for p in texto.split("\n\n") if p.strip()]
    chunks: list[str] = []
    actual = ""
    for parrafo in parrafos:
        candidato = f"{actual}\n\n{parrafo}" if actual else parrafo
        if len(candidato) > limite_caracteres and actual:
            chunks.append(actual.strip())
            actual = parrafo
        else:
            actual = candidato
    if actual.strip():
        chunks.append(actual.strip())
    return chunks


def indexar_nota(ruta: str, titulo: str, tags: list[str], contenido: str) -> int:
    """Indexa (o reindexa) una nota entera en Chroma, chunk por chunk.

    Si la nota ya tenia chunks de una version anterior (por ejemplo, se
    esta re-guardando con el mismo ``ruta``), los borra primero -- si
    no, editar una nota dejaria "fantasmas" de la version vieja
    apareciendo en las busquedas. Esto es lo que hace que el reindexado
    sea "incremental": indexar una nota no toca el resto del indice.

    Devuelve la cantidad de chunks indexados (0 si la nota esta vacia).
    """
    coleccion = _coleccion()
    coleccion.delete(where={"ruta": ruta})

    chunks = dividir_en_chunks(contenido)
    if not chunks:
        return 0

    vectores = _embeber(chunks, tipo_entrada="document")
    ids = [f"{ruta}::{i}" for i in range(len(chunks))]
    # Chroma solo acepta str/int/float/bool como metadata -- una lista
    # de tags no entra, por eso se guarda como texto separado por comas.
    metadatas = [{"ruta": ruta, "titulo": titulo, "tags": ", ".join(tags)} for _ in chunks]

    coleccion.add(
        ids=ids,
        embeddings=vectores,  # type: ignore[arg-type]
        documents=chunks,
        metadatas=metadatas,  # type: ignore[arg-type]
    )
    return len(chunks)


def buscar_semantico(consulta: str, top_k: int = 3) -> list[str]:
    """Busca los chunks cuyo significado esta mas cerca de la consulta.

    Devuelve el texto de cada chunk encontrado (no la nota entera) --
    seguis el patron "mensajero" del diseño: se le pasa al modelo solo
    el fragmento puntual, no la boveda completa.
    """
    coleccion = _coleccion()
    if coleccion.count() == 0:
        return []

    vector = _embeber([consulta], tipo_entrada="query")[0]
    resultado = coleccion.query(
        query_embeddings=[vector],  # type: ignore[arg-type]
        n_results=min(top_k, coleccion.count()),
    )
    documentos = resultado.get("documents") or [[]]
    return list(documentos[0])


def _parsear_nota(texto: str) -> tuple[str, list[str], str]:
    """Separa una nota guardada en (titulo, tags, cuerpo).

    Asume el formato que arma ``mcp_obsidian.operaciones.crear_nota``:
    frontmatter, despues "# Titulo", despues el contenido.
    """
    match_tags = re.search(r"^tags: \[(.*?)\]$", texto, flags=re.MULTILINE)
    tags = [t.strip() for t in match_tags.group(1).split(",") if t.strip()] if match_tags else []

    match_titulo = re.search(r"^# (.+)$", texto, flags=re.MULTILINE)
    titulo = match_titulo.group(1).strip() if match_titulo else "Sin titulo"
    cuerpo = texto[match_titulo.end() :].strip() if match_titulo else texto

    return titulo, tags, cuerpo


def reindexar_todo() -> int:
    """Reindexa TODAS las notas de la boveda desde cero.

    A diferencia de ``indexar_nota`` (incremental, la dispara el
    Archivista al guardar), esta funcion recorre toda la boveda. Uso
    manual: hace falta si cambiaste el modelo de embeddings o el
    esquema de chunking y necesitas regenerar el indice entero.

    Devuelve la cantidad total de chunks indexados.
    """
    total = 0
    for ruta in operaciones.listar_carpeta(""):
        titulo, tags, cuerpo = _parsear_nota(operaciones.leer_nota(ruta))
        total += indexar_nota(ruta, titulo, tags, cuerpo)
    return total


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    cantidad = reindexar_todo()
    print(f"Reindexados {cantidad} chunks en total.")
