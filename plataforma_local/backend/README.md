# FireCal Perú — backend local

Backend del geovisor **FireCal Perú** (NASA Space Apps 2026, reto *Harmonization of MODIS and VIIRS Hot Spots*).
Calcula un **calendario de actividad de quema** (año × mes) armonizado entre MODIS y VIIRS, la anomalía del mes
frente a la mediana histórica, la descarga de focos por área de interés (AOI) y, más adelante, una perspectiva del
mes siguiente. El frontend consume la API en `http://localhost:8000`.

> **Plataforma del prototipo (desde 14-nov):** este backend sirve los **datos reales de Cusco** armonizados por
> Antonio (`MAESTRO.md`, `data/harmonized/`) con `GET /api/calendario | anomalias | hotspots.csv | metadatos` y el
> frontend Leaflet en `http://localhost:8000/`. Guía vigente: [`../README.md`](../README.md). Lo que sigue en este
> archivo describe el **backend anterior** (pipeline sintético, `/api/v1`), hoy desactivado (`api.legacy_v1: false`).

> **Estado actual:** pipeline y API completos en **modo sintético** (Fases 0–6). Pendiente: modelo de perspectiva
> (Fase 7; hoy `/forecast` responde `available: false`), empaquetado Docker (Fase 8) y datos reales de FIRMS
> (Fase R). **Los datos sintéticos son simulados: no usar para decisiones.**

Documentación adicional: [`docs/API.md`](docs/API.md) (contratos para el frontend) ·
[`docs/METODOLOGIA.md`](docs/METODOLOGIA.md) (armonización y validación) · [`CLAUDE.md`](CLAUDE.md) (notas técnicas).

---

## 1. Qué hay que instalar

### Software

| Software | Versión | ¿Obligatorio? | Para qué | Cómo instalar (Windows) |
| --- | --- | --- | --- | --- |
| **Python** | **3.12** (3.11 también sirve) | Sí | Todo el backend | [python.org](https://www.python.org/downloads/) o `winget install Python.Python.3.12` |
| **Git** | cualquiera reciente | Sí | Clonar el repositorio | `winget install Git.Git` |
| GNU **make** | 4.x | No | Atajos (`make test`, `make serve`…) | `winget install ezwinports.make` |
| Editor (VS Code) | — | No | Editar código | `winget install Microsoft.VisualStudioCode` |

- **No uses Python 3.13 o superior por ahora:** algunas librerías (p. ej. `lightgbm`) pueden no tener versión
  compilada para ellas. En Windows, si tienes varias versiones, el lanzador `py -3.12` elige la correcta.
- Funciona en **Windows 10/11 (PowerShell)**, Linux, macOS y WSL2.
- Recursos: ~1 GB libre en disco (entorno ~620 MB + datos ~200 MB) y 4 GB de RAM o más.
- **No hace falta:** base de datos externa, Docker, conexión a internet (salvo para instalar), MAP_KEY de FIRMS
  ni Google Earth Engine. Todo corre localmente con DuckDB (un archivo).

### Librerías de Python

Se instalan solas con `pip` desde `pyproject.toml` (paso 2.3). Versiones probadas en
[`requirements-lock.txt`](requirements-lock.txt):

| Librería | Versión probada | Uso en el proyecto |
| --- | --- | --- |
| `fastapi` | 0.162.5 | API web |
| `uvicorn[standard]` | 0.54.0 | Servidor de la API |
| `pydantic` / `pydantic-settings` | 2.14.3 / 2.16.2 | Validación de datos y configuración (`.env`, YAML) |
| `duckdb` | 2.0.0 | Base de datos local (`data/processed/firecal.duckdb`) |
| `pandas` / `numpy` / `pyarrow` | 3.1.1 / 2.5.4 / 26.0.1 | Tablas y cálculo |
| `h3` | 4.5.0 | Rejilla hexagonal (celdas H3) |
| `shapely` / `pyproj` | 2.2.0 / 3.8.0 | Geometrías, áreas y buffers |
| `typer` | 0.29.1 | Línea de comandos `firecal` |
| `pyyaml` | 6.0.3 | Parámetros científicos (`config/settings.yaml`) |
| `httpx` | 0.28.1 | Cliente HTTP (descarga NRT de FIRMS, pendiente) |
| `scikit-learn` / `lightgbm` | 1.9.1 / 4.7.0 | Modelo de perspectiva (Fase 7) |
| `matplotlib` | 3.11.2 | Gráficos de validación (`reports/*.png`) |
| `tzdata` | 2026.6 | Zona horaria America/Lima en Windows (viene con pandas) |
| `pytest` / `ruff` | 9.2.0 / 0.17.4 | Tests y linter (solo desarrollo, extra `dev`) |

---

## 2. Cómo ejecutar la plataforma localmente (paso a paso)

Los comandos están para **PowerShell en Windows**; al final de cada paso va el equivalente en Linux/macOS.

### 2.1 Clonar el repositorio

```powershell
git clone https://github.com/Jyron1310/project_nasa.git
cd project_nasa
git checkout backend
cd backend
```

### 2.2 Crear el entorno virtual (solo la primera vez)

```powershell
py -3.12 -m venv .venv
```
Linux/macOS: `python3.12 -m venv .venv`

### 2.3 Instalar las dependencias (solo la primera vez, ~2-5 min)

```powershell
.\.venv\Scripts\python -m pip install --upgrade pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```
Para usar exactamente las versiones probadas:
`.\.venv\Scripts\python -m pip install -r requirements-lock.txt` y luego
`.\.venv\Scripts\python -m pip install -e . --no-deps`.

Linux/macOS: igual, cambiando `.\.venv\Scripts\python` por `.venv/bin/python`. Con make: `make install`.

### 2.4 Configuración (opcional)

```powershell
Copy-Item .env.example .env
```
Por defecto todo funciona sin `.env` (modo `synthetic`). Los parámetros científicos están en
`config/settings.yaml`.

### 2.5 Activar UTF-8 en la sesión (Windows, cada vez que abras PowerShell)

```powershell
$env:PYTHONUTF8 = "1"
```
Evita problemas con tildes en la consola de Windows. Con `make` se activa solo.

### 2.6 Generar los datos y correr el pipeline (~1-2 min)

```powershell
.\.venv\Scripts\firecal all --mode synthetic
```
Hace todo en orden (~3-4 min): simula los focos (`data/synthetic/`), los carga y limpia, agrega por celda H3, armoniza
MODIS/VIIRS, valida (`reports/harmonization_metrics.json` + gráficos) y precalcula las respuestas de la demo.
Al final arma los eventos del plan (Parquet en `data/processed/eventos/`). Debe terminar con
`OK all (synthetic) en ~200 s` (región de 5 departamentos). Solo hay que repetirlo si cambian el código o los parámetros.

Con make: `make all-synthetic`. Linux/macOS: `.venv/bin/firecal all --mode synthetic`.

### 2.7 Levantar la API

```powershell
.\.venv\Scripts\firecal serve
```
- Web (frontend Leaflet): `http://localhost:8000`
- API del plan: `http://localhost:8000/api/calendario?departamento=PE-CUS`
- Documentación interactiva (probar endpoints desde el navegador): `http://localhost:8000/docs`
- Para detenerla: `Ctrl + C`. Otro puerto: `firecal serve --port 8001`.

Con make: `make serve`.

### 2.8 Comprobar que funciona

En otra ventana de PowerShell (con la API corriendo):

```powershell
Invoke-RestMethod http://localhost:8000/health
# -> status: ok, data_mode: synthetic, data_ready: True

Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/calendar `
  -ContentType "application/json" -Body '{"aoi": {"type": "region", "code": "PE-CUS"}}'
```
Linux/macOS: `curl http://localhost:8000/health`.

### 2.9 Conectar el frontend

El frontend (MapLibre + Terra Draw + ECharts) debe apuntar a `http://localhost:8000`. CORS ya permite
`http://localhost:5173` (Vite) y `http://localhost:3000`; otros orígenes se agregan en
`config/settings.yaml → api.cors_origins`. Contratos y ejemplos: [`docs/API.md`](docs/API.md).

### 2.10 Correr los tests (opcional, ~1 min)

```powershell
.\.venv\Scripts\python -m ruff check .
.\.venv\Scripts\python -m pytest -q
```
Con make: `make lint` y `make test`.

---

## 3. Endpoints disponibles

### 3.1 Endpoints del plan (GET, alternativas A + C)

| Método | Ruta | Devuelve |
| --- | --- | --- |
| GET | `/api/departamentos` | Departamentos procesados (código ISO, nombre, área) |
| GET | `/api/calendario` | Matriz año × mes de eventos deduplicados y anomalía normalizada por era |
| GET | `/api/anomalias` | Un mes frente a la mediana del mismo mes en su era |
| GET | `/api/hotspots.csv` | Eventos armonizados del rango (máx. 5 años) |
| GET | `/api/metadatos` | Versión, reglas, umbral de confianza, cobertura y créditos |

AOI: `departamento=PE-CUS`, `bbox=oeste,sur,este,norte` o `lat`, `lon`, `radio_km`. Cada respuesta trae la
cabecera `X-Process-Time-ms`. Detalle en [`docs/API.md`](docs/API.md#endpoints-del-plan-get-api).

### 3.2 Endpoints de la alternativa B (backend anterior)

| Método | Ruta | Devuelve |
| --- | --- | --- |
| GET | `/health` | Estado, modo de datos y si el pipeline ya corrió |
| GET | `/api/v1/regions` | Regiones con geometría simplificada (GeoJSON) |
| POST | `/api/v1/calendar` | Matriz año × mes (`harmonized`, `percentile`, `raw_modis`, `raw_viirs`) |
| POST | `/api/v1/anomaly` | Un mes frente a su mediana histórica |
| POST | `/api/v1/hotspots` | Focos del AOI en CSV (streaming, abre en Excel) o GeoJSON |
| POST | `/api/v1/map/cells` | Hexágonos H3 con el valor armonizado de un mes (GeoJSON) |
| POST | `/api/v1/forecast` | Perspectiva del mes siguiente (`available: false` hasta la Fase 7) |
| GET | `/api/v1/meta` | Unidad, banda de incertidumbre, armonización, validación y límites |

Toda respuesta JSON incluye `data_mode`, `data_version`, `generated_at` y `notes`.

---

## 4. Comandos de la CLI

En PowerShell sin make, antepón `.\.venv\Scripts\` (p. ej. `.\.venv\Scripts\firecal synth`).

| Atajo make | Comando | Qué hace |
| --- | --- | --- |
| `make all-synthetic` | `firecal all --mode synthetic` | Todo el pipeline (~1-2 min) |
| `make synth` | `firecal synth` | Genera focos sintéticos en `data/synthetic/` (~1.3 M filas) |
| — | `firecal ingest` | Carga los CSV del modo actual en DuckDB |
| — | `firecal build --step clean\|aggregate\|harmonize` | Limpieza, agregación H3, armonización (sin `--step`: los tres) |
| — | `firecal validate` | Reporte de validación + gráficos en `reports/` |
| — | `firecal plan-events` | Eventos del plan (A: 1 km + deduplicación) -> Parquet por año/mes (~7 s) |
| `make precompute` | `firecal precompute` | Respuestas por región precalculadas (demo instantánea) |
| `make serve` | `firecal serve` | API en http://localhost:8000 |
| `make test` / `make lint` | `pytest -q` / `ruff check .` | Tests y linter |
| — | `firecal --help` | Lista los comandos |

---

## 5. Modos de datos

Se eligen con `FIRECAL_DATA_MODE` en `.env`:

- `synthetic` (por defecto): focos simulados con el formato de FIRMS. No necesita MAP_KEY ni descargas.
- `real` (**en desarrollo, Fase R**): CSV históricos de FIRMS en `data/raw/firms/`. La descarga NRT con
  `FIRMS_MAP_KEY` aún no está implementada, y los supuestos sobre el formato real de FIRMS están sin verificar
  (lista en `CLAUDE.md`, sección "Fase R").

La API etiqueta cada respuesta con el modo con que se generaron los datos (`"data_mode"`).

---

## 6. Problemas frecuentes

| Síntoma | Solución |
| --- | --- |
| `py -3.12` no existe / se usa otra versión | Instala Python 3.12 y vuelve a crear `.venv` (paso 2.2). |
| `firecal` no se reconoce | Usa la ruta completa `.\.venv\Scripts\firecal` (no hace falta activar el entorno). |
| Tildes raras en la consola | `$env:PYTHONUTF8 = "1"` en la sesión (paso 2.5). |
| `/health` dice `data_ready: false` o la API responde 503 | Corre el pipeline (paso 2.6). |
| La web abre pero el calendario dice 503 | Faltan los eventos del plan: `firecal plan-events`. |
| Cambié de departamentos | `python scripts/build_regions.py <códigos>`, copia el bbox en `settings.yaml` y corre `firecal all`. |
| `address already in use` al levantar la API | Otro proceso usa el puerto 8000: `firecal serve --port 8001`. |
| Error de archivo en uso al correr el pipeline | Cierra programas que tengan abierto `data/processed/firecal.duckdb` (p. ej. un visor de DuckDB). |
| El CSV se ve en una sola columna en Excel | Excel usa `;` como separador en tu configuración: *Datos → Desde texto/CSV*. |
| `make` no se reconoce | Es opcional: usa los comandos equivalentes o `winget install ezwinports.make`. |
