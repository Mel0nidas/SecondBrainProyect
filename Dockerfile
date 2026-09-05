# Imagen para correr en AWS Fargate (DISEÑO.md, Fase 6).
#
# Usa "uv" (el mismo gestor de paquetes que ya usás en tu compu) tambien
# adentro del contenedor, para que la version de las dependencias sea
# EXACTAMENTE la misma que corriste y testeaste localmente (gracias a
# uv.lock).

FROM python:3.12-slim

# Copia el binario de "uv" desde su propia imagen oficial -- mas rapido
# y confiable que instalarlo con pip adentro de esta imagen.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Se copian PRIMERO solo los archivos de dependencias (no el codigo).
# Docker cachea cada paso: mientras no cambien pyproject.toml/uv.lock,
# este paso (el mas lento, instala ~130 paquetes) no se vuelve a correr
# aunque edites el codigo de src/ despues.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Ahora si, el codigo.
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# Uvicorn escucha en el puerto 8000 adentro del contenedor. Fargate lo
# mapea hacia afuera segun como se configure el Service (no hace falta
# tocar nada aca para eso).
EXPOSE 8000

# "--host 0.0.0.0" es obligatorio en un contenedor: sin esto, uvicorn
# solo escucha pedidos que vengan de DENTRO del propio contenedor, y
# Fargate no podria mandarle trafico desde afuera.
CMD ["uv", "run", "uvicorn", "app.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
