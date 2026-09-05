"""Punto de entrada de consola: `uv run python -m grafo` (Fase 2).

Lee las variables de entorno del archivo .env (tus API keys), arma el
grafo (Router + Archivista + Bibliotecario + directo), y le pasa el
mensaje que le pasaste por linea de comandos.
"""

import sys

from dotenv import load_dotenv

from grafo.estado import Estado
from grafo.grafo import construir_grafo

MENSAJE_POR_DEFECTO = "/ayuda"


def main() -> None:
    load_dotenv()  # busca un archivo .env en la carpeta y carga sus variables

    mensaje = " ".join(sys.argv[1:]) or MENSAJE_POR_DEFECTO

    grafo = construir_grafo()
    # recursion_limit generoso: el corte real lo hace nuestro Presupuesto
    # (verificar_presupuesto), no el limite de seguridad generico de
    # langgraph -- si no, langgraph podria cortar primero con un error
    # feo en vez de nuestro resumen prolijo.
    estado_final = grafo.invoke(Estado(mensaje_usuario=mensaje), config={"recursion_limit": 100})

    print(f"Vos escribiste: {mensaje}")
    print(estado_final["respuesta_final"])


if __name__ == "__main__":
    main()
