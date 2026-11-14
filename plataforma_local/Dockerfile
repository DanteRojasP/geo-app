# FireCal Perú: API (FastAPI) + frontend estático (Leaflet) en una sola imagen.
# Construir desde local_plat/:  docker build -t firecal .
# Correr:                        docker run --rm -p 8000:8000 firecal
#
# Datos: por defecto se generan en la construcción (modo sintético, ~3-4 min) para que la imagen
# arranque al instante en la nube. Con --build-arg BUILD_DATA=0 la imagen sale sin datos y el
# contenedor los genera al arrancar (o se monta un volumen en /app/backend/data).

FROM python:3.12-slim AS base
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 FIRECAL_DATA_MODE=synthetic
WORKDIR /app/backend

# libgomp1: lo necesita lightgbm (modelo de la Fase 7) en Debian slim.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-lock.txt ./
RUN pip install -r requirements-lock.txt

COPY backend/ ./
COPY frontend/ /app/frontend/
RUN pip install -e . --no-deps

ARG BUILD_DATA=1
RUN if [ "$BUILD_DATA" = "1" ]; then firecal all --mode synthetic && rm -rf data/synthetic data/interim; fi

# Usuario sin privilegios; data/ escribible para regenerar en el arranque si hace falta.
RUN useradd --create-home --uid 10001 firecal && mkdir -p data && chown -R firecal /app/backend/data
USER firecal

EXPOSE 8000
# PORT lo fijan Azure Container Apps / Cloud Run / App Service; 8000 por defecto.
# En la nube, FIRECAL_TRUST_PROXY=1 para limitar por la IP real del cliente (api/limits.py).
# No se usa --forwarded-allow-ips='*': haría que uvicorn creyera IPs inventadas por el cliente.
CMD ["sh", "-c", "[ -f data/processed/eventos_meta.json ] || firecal all --mode synthetic; exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
