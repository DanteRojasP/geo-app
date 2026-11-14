# Despliegue en internet: falencias actuales, riesgos y procedimiento

Análisis hecho sobre la plataforma local (`local_plat`) al 14-nov-2026. Las cifras de memoria, latencia y tamaño
se midieron en esta máquina en modo sintético.

## 1. Mediciones de partida

| Medida | Valor |
| --- | --- |
| RAM del servidor (API + datos de Cusco) | ~170 MB en Docker (antes ~250-275 MB con el modo sintético) |
| Datos procesados | ~5 MB de Parquet (CSV de Cusco: 10 MB) |
| Imagen Docker | 1,32 GB; se construye en ~1,5 min |
| Carga de datos (`firecal plan-events`) | ~2 s |
| Latencia de `/api/calendario` | 1.ª consulta de un AOI: 160-540 ms; repetida: ~7 ms (caché en memoria) |
| `/api/v1/calendar` (alternativa B, precalculada) | ~27 ms |

## 2. Falencias que existen hoy (hay que resolverlas antes de publicar)

| # | Falencia | Por qué importa en internet | Qué hacer |
| --- | --- | --- | --- |
| 1 | ~~**Solo datos sintéticos.**~~ **RESUELTA (14-nov):** la plataforma usa los datos reales de NASA FIRMS armonizados por Antonio (Cusco, 2000-11-04 a 2025-12-31), validados contra MAESTRO §6 en cada carga y en la construcción de Docker. | — | Serie histórica: no incluye 2026 (decisión del equipo). Ampliar a otras regiones exige recalibrar k y kT (MAESTRO P7). |
| 2 | ~~**Imagen Docker sin probar.**~~ **RESUELTA.** `firecal-peru:local` se construye en ~3 min la primera vez y ~1,5 min después (caché); pesa 1,57 GB; el pipeline corre dentro en ~75 s; el contenedor usa ~240 MB de RAM. Probados la web, los endpoints, el CSV y los límites (429). | Es la pieza que se despliega en la nube. | Reducir el tamaño: sacar `lightgbm`, `scikit-learn` y `matplotlib` de la imagen de la API (solo los usan la validación y la Fase 7). |
| 3 | ~~**Sin límite de solicitudes.**~~ **RESUELTA** (ver sección 5). | `/api/hotspots.csv` y los AOI dibujados consumen CPU: unos pocos clientes podían saturar el contenedor. | Protocolo de solicitudes en `backend/api/limits.py`: cubeta de fichas por IP (429), semáforo de consultas pesadas (503), candado por clave y máximo de filas por CSV. |
| 4 | **CORS solo permite localhost.** | Si el frontend se sirve desde otro dominio (p. ej. el hosting de GoDaddy), el navegador bloquea la API. | Mientras frontend y API vayan en la misma imagen y dominio, no hace falta. Si se separan: agregar el dominio en `settings.yaml → api.cors_origins` y abrir la web con `?api=https://dominio-api`. |
| 5 | **Mapa base de OpenStreetMap** (`tile.openstreetmap.org`). | La política de uso de OSM no permite tráfico alto de una app pública; pueden bloquear el sitio. | Para el demo vale. En producción: un proveedor con clave (Azure Maps o Google Maps, ver beneficios) o MapTiler o Esri. Solo cambia la URL en `app.js`. |
| 6 | **Datos dentro de la imagen.** Para actualizar se reconstruye y se vuelve a desplegar. | Con datos reales NRT (diarios) habría que reconstruir cada día. | Fase R: tarea programada (Azure Container Apps Job o Cloud Run Job) que corra el pipeline y suba `data/processed` a Blob Storage o Cloud Storage. La API lo lee al arrancar o lo monta como volumen. |
| 7 | ~~**Arranque sin datos = 3-4 min.**~~ **RESUELTA:** cargar los datos de Cusco toma ~2 s y la imagen ya los trae validados. | — | — |
| 8 | **Arranque en frío.** | Si la nube apaga el contenedor (escala a cero), la primera visita espera varios segundos y la primera consulta de cada AOI tarda ~0,5 s. | Mínimo 1 réplica durante el concurso. Opcional: precalentar los 5 departamentos al arrancar. |
| 9 | **Memoria por réplica.** Cada proceso carga sus propios datos (~275 MB). | Con 512 MB no hay margen; con varios workers se multiplica. | 1 GB de RAM y 1 worker por contenedor; escalar con réplicas, no con workers. |
| 10 | **`/docs` público.** | Expone toda la API (es útil para el jurado, pero también para abusar de ella). | Dejarlo durante el concurso. Después: `docs_url=None` o protegerlo. |
| 11 | **Sin monitoreo ni logs centralizados.** | No sabrías si el sitio cae durante la evaluación. | Application Insights (Azure) o Cloud Logging (GCP) y un *health check* a `/health`. |
| 12 | **`C:\` es un repositorio git** y `local_plat` no tiene un repositorio propio. | Riesgo de commits accidentales de todo el disco, y el código nuevo no tiene control de versiones. | Crear un repositorio para `local_plat` (o una rama en `project_nasa`) con `.gitignore` para `.venv/` y `data/`. |

## 3. Falencias que pueden aparecer (riesgos del método y de los datos reales)

| Riesgo | Detalle | Mitigación |
| --- | --- | --- |
| Formato real de FIRMS distinto al supuesto | Códigos de `satellite`, `version` (SP/NRT), confianza VIIRS y `type`: todo está marcado `TODO-REAL` en `firecal/etl/firms_schema.py`. | Descargar una muestra real de cada producto y ajustar antes de cargar todo. |
| Límites de la API de FIRMS | La MAP_KEY tiene un cupo de transacciones por intervalo y la API `area` limita los días por solicitud (verificar los valores actuales en la página de FIRMS). | Descarga incremental con reintentos y respuestas crudas guardadas (`data/raw/firms/nrt/`). |
| Fin de las misiones Terra y Aqua | Si MODIS deja de entregar datos, aparece una **tercera era** ("solo VIIRS") con pocos años: la anomalía C no tendría historia suficiente. | Agregar la era en `era_of()`. Mientras no haya 5 años, usar la alternativa B (calibración VIIRS → MODIS-Aqua) para enlazar la serie. |
| Deriva orbital (Terra y Aqua) | Cambia la hora de paso y, con ella, los conteos desde ~2020-2022. A + C no lo corrige. | Mostrarlo en la metodología (ya está en `/api/metadatos`) o usar B. |
| Cambio S-NPP → NOAA-20 | La cadena de un solo VIIRS cambia de satélite al terminar S-NPP. | En el backend B la razón N20/S-NPP es ~0,99 en simulación; con datos reales, verificarla. |
| Límites departamentales simplificados | geoBoundaries "simplified": los focos a pocos cientos de metros del borde pueden quedar en el departamento vecino. | Para conteos oficiales, usar los límites del INEI y la versión sin simplificar. |
| Uso indebido como dato oficial | Un tercero puede citar los números. | Aviso de datos sintéticos o provisionales, créditos de FIRMS y nota "focos de calor, no número de incendios" (ya están). |

## 4. Procedimiento de despliegue recomendado

Arquitectura simple: **una sola imagen** (API + frontend) en un servicio de contenedores con HTTPS administrado, y un
dominio propio apuntando a ella.

### Opción A: Azure Container Apps (beneficio Microsoft Azure)

```powershell
# 1) Probar la imagen localmente
cd "C:\Nubel\local base\local_plat"
docker compose up --build
# 2) Crear recursos y desplegar (Azure CLI: winget install Microsoft.AzureCLI)
az login
az group create -n firecal-rg -l eastus2
az acr create -n firecalacr<sufijo> -g firecal-rg --sku Basic
az acr build -r firecalacr<sufijo> -t firecal:v1 .
az containerapp up -n firecal -g firecal-rg --image firecalacr<sufijo>.azurecr.io/firecal:v1 \
  --target-port 8000 --ingress external
az containerapp update -n firecal -g firecal-rg --min-replicas 1 --max-replicas 2 --cpu 0.5 --memory 1.0Gi
```

### Opción B: Google Cloud Run (beneficio Google Cloud; proyecto `sonic-mile-514718-r5` listo)

El `Dockerfile` está en `plataforma_local/` y usa la **raíz del repositorio** como contexto. Por eso se
construye en local y se sube la imagen, en lugar de usar `--source`:

```powershell
# Desde la raíz del repositorio (una sola vez: crear el repositorio de imágenes)
gcloud artifacts repositories create firecal --repository-format=docker --location=southamerica-east1
gcloud auth configure-docker southamerica-east1-docker.pkg.dev

# Construir, subir y desplegar
$IMG = "southamerica-east1-docker.pkg.dev/sonic-mile-514718-r5/firecal/firecal-cusco:v1"
docker build -f plataforma_local/Dockerfile -t $IMG .
docker push $IMG
gcloud run deploy firecal --image $IMG --region southamerica-east1 --memory 1Gi `
  --min-instances 1 --max-instances 2 --allow-unauthenticated `
  --set-env-vars FIRECAL_TRUST_PROXY=1,FIRECAL_PROXY_HOPS=2
```
Cloud Run define `PORT` y la imagen lo respeta. Después de la evaluación: `--min-instances 0` o borrar el servicio.

### Dominio (beneficio GoDaddy Registry)

1. Registrar un dominio no premium gratis (1 año, con SSL).
2. En el servicio de nube, agregar el dominio personalizado (Container Apps: *Custom domains*; Cloud Run: *Domain mappings*).
3. Crear en el DNS del registrador los registros que indique la nube (CNAME/TXT o A/AAAA). El certificado HTTPS lo
   emite la nube.

### Lista de verificación antes de publicar

- [ ] `docker compose up --build` funciona y la web carga en `http://localhost:8000`.
- [ ] `pytest -q` en verde.
- [ ] Aviso de datos sintéticos visible (o datos reales cargados y verificados).
- [ ] Mapa base con proveedor y clave propios, o aceptado el riesgo de OSM para el demo.
- [ ] Mínimo 1 réplica, 1 GB de RAM, *health check* a `/health`.
- [ ] Alertas de costo o presupuesto configuradas en la nube.
- [ ] Ninguna clave (MAP_KEY, Azure Maps, Meteomatics) en el repositorio ni en la imagen: van como variables o
      secretos del servicio.

## 5. Protocolo de solicitudes (falencia 3, implementado)

Archivo: `backend/api/limits.py` (+ `backend/firecal/concurrency.py`). Solo usa `threading`, sin dependencias nuevas.
Parámetros: `config/settings.yaml → api.rate_limit` y `api.max_csv_rows`.

| Barrera | Primitiva | Qué hace | Respuesta |
| --- | --- | --- | --- |
| Cubeta general por cliente | `threading.Lock` + diccionario de cubetas | 40 solicitudes de golpe y luego 120/min por IP en `/api/*` (`/health` y la web no cuentan) | **429** + `Retry-After` |
| Cubeta de pesadas por cliente | ídem | CSV, celdas H3 y AOI dibujados: 5 de golpe y luego 10/min | **429** + `Retry-After` |
| Turnos de pesadas (todo el proceso) | `threading.BoundedSemaphore(2)` | Como mucho 2 pesadas a la vez; las demás esperan 2 s su turno. En el CSV el turno se libera al terminar de enviarlo (o si el cliente corta) | **503** + `Retry-After` |
| Candado por clave | un `threading.Lock` por AOI (`SingleFlight`) | N solicitudes iguales sin caché: calcula una y las demás reutilizan | — |
| Tope de filas | conteo previo en DuckDB | CSV de más de 200 000 filas | **422** con el motivo |

- Estado en vivo: `GET /health/limits` (clientes, rechazos 429/503, pesadas en curso).
- Cabeceras: `X-RateLimit-Remaining`, `Retry-After`, `X-Process-Time-ms`.
- **Detrás de un proxy** (Azure Container Apps, Cloud Run): definir `FIRECAL_TRUST_PROXY=1`. La IP real se toma desde
  la **derecha** de `X-Forwarded-For` (`proxy_hops`, por defecto 1), porque las IPs de la izquierda las puede inventar
  el cliente. Sin esa variable la cabecera se ignora (en local cualquiera podría falsificarla). Confirmar en la
  plataforma elegida cuántos proxies agregan IP y ajustar `proxy_hops`.
- Límite conocido: los contadores viven en la memoria de **cada réplica**. Con 2 réplicas el límite efectivo por IP
  se duplica. Para el demo basta; para producción, un límite compartido en el gateway o en Redis.
- Pruebas: `backend/tests/test_limits.py` (hilos concurrentes, 429, 503, IP falsificada, liberación del turno).

## 6. Cambios del 14-nov (integración con Antonio)

- Datos reales de Cusco en lugar de sintéticos (falencia 1), carga en ~2 s (falencia 7).
- Docker: los CSV entran como **contextos adicionales** (`docker-compose.yml → additional_contexts`) desde la raíz
  del repositorio, sin duplicarlos en `plataforma_local/`. La construcción corre `firecal plan-events`, que falla si
  los datos no coinciden con MAESTRO §6.
- Para Cloud Run o Azure: construir desde la raíz del repo (para que los contextos existan) o usar la imagen ya
  construida (`docker compose build`, luego `docker push` al registro de la nube).
- El backend anterior sintético (`/api/v1`) quedó apagado (`api.legacy_v1: false`): no hay datos simulados expuestos.

## 7. Cambios del 14-nov (noche): interfaz de Dante y Dockerfile de Antonio

- **Dockerfile** basado en `Dockerfile.modelo` de Antonio: contexto = raíz del repositorio y datos dentro de la
  imagen. Se agregaron una etapa Node que compila la interfaz y la validación con `firecal plan-events`.
  Imagen de 1,33 GB, ~130 MB de RAM y construcción de ~2 min.
- **Interfaz** de Dante (React + MapLibre) servida por la misma API: no hace falta CORS mientras vayan juntas.
- **Tiles externos:** el mapa base usa OpenFreeMap y la vista satelital Esri World Imagery. Ambos son gratuitos
  con atribución; para tráfico alto, revisar sus condiciones de uso (falencia 5).
