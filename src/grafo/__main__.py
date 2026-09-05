"""Punto de entrada de consola: `uv run python -m grafo`.

Lee las variables de entorno del archivo .env (tus API keys), arma el
grafo, le manda un mensaje a Claude y muestra la respuesta.
"""

import sys

from dotenv import load_dotenv

from grafo.estado import EstadoSaludo
from grafo.grafo import construir_grafo

MENSAJE_POR_DEFECTO = "Decime en una sola oracion que sos un grafo de LangGraph."


def main() -> None:
    load_dotenv()  # busca un archivo .env en la carpeta y carga sus variables

    mensaje = " ".join(sys.argv[1:]) or MENSAJE_POR_DEFECTO

    grafo = construir_grafo()
    estado_final = grafo.invoke(EstadoSaludo(mensaje_usuario=mensaje))

    print(f"Vos preguntaste: {mensaje}")
    print(f"Claude respondio: {estado_final['respuesta']}")


if __name__ == "__main__":
    main()
