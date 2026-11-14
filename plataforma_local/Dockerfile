# FireCal Cusco: API (FastAPI) + frontend estático (Leaflet) + datos armonizados de Cusco.
#
# Los datos NO están en esta carpeta: son los CSV de Antonio en la raíz del repositorio
# (data/harmonized/ y harmonizacion/cusco_ref/). Se pasan como contextos adicionales:
#   docker compose up --build                       (ya los define docker-compose.yml)
#   docker build -t firecal-cusco \
#     --build-context harmonized=../data/harmonized \
#     --build-context cusco_ref=../harmonizacion/cusco_ref .
# En la construcción se validan contra las sumas de control de MAESTRO §6 (si no coinciden,
# la construcción falla).

FROM python:3.12-slim
ENV PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app/backend

# libgomp1: lo necesita lightgbm (dependencia del backend anterior) en Debian slim.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-lock.txt ./
RUN pip install -r requirements-lock.txt

COPY backend/ ./
COPY frontend/ /app/frontend/
RUN pip install -e . --no-deps

# Datos de Cusco (MAESTRO.md): mismos caminos relativos que en el repositorio.
COPY --from=harmonized . /app/data/harmonized/
COPY --from=cusco_ref . /app/harmonizacion/cusco_ref/
RUN firecal plan-events

# Usuario sin privilegios.
RUN useradd --create-home --uid 10001 firecal && chown -R firecal /app/backend/data
USER firecal

EXPOSE 8000
# PORT lo fijan Azure Container Apps / Cloud Run / App Service; 8000 por defecto.
# En la nube, FIRECAL_TRUST_PROXY=1 para limitar por la IP real del cliente (api/limits.py).
# No se usa --forwarded-allow-ips='*': haría que uvicorn creyera IPs inventadas por el cliente.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
