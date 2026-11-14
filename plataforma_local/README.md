# FireCal Perú: plataforma local (guía)

Implementación local del **plan de trabajo** (`NASA_CLAUDE_TEAM/PLAN.md`) para el reto *Calendario de incendios
armonizado (MODIS + VIIRS)*, NASA Space Apps 2026. Toma como motor el backend de pruebas anterior
(`project_nasa`, rama `backend`) y le agrega lo que pide el plan:

| Pide el plan | Dónde está |
| --- | --- |
| AOI por **departamento del Perú** (dibujo opcional) | `config/regions/peru_departamentos.geojson` + frontend |
| Armonización **A** (grilla común de 1 km + deduplicación por mayor FRP) | `backend/firecal/plan/events.py` |
| Armonización **C** (anomalías normalizadas) | `backend/firecal/plan/query.py` |
| Alternativa **B** (calibración por solapamiento), opcional | ya existía en el backend anterior: `/api/v1/*` |
| **Parquet** particionado por año y mes, consultado con DuckDB | `backend/data/processed/eventos/anio=*/mes=*/` |
| 4 endpoints (`/api/calendario`, `/api/anomalias`, `/api/hotspots.csv`, `/api/metadatos`) | `backend/api/routers/plan.py` |
| Mensajes de error claros (AOI vacío, rango invertido, sin datos, área demasiado grande) | `PlanError` / `PlanNoData` (422 / 404) |
| Frontend Leaflet + calendario mes × año (viridis) + descarga CSV + créditos FIRMS | `frontend/` |
| Latencia medida en ms | cabecera `X-Process-Time-ms` en cada respuesta (se muestra en la página) |
| Pruebas de lógica (conteos, deduplicación, mediana, anomalía, CSV) | `backend/tests/test_plan.py` |
| Protocolo de solicitudes (límite por IP, turnos para consultas pesadas, candados) | `backend/api/limits.py`; estado en `GET /health/limits` |

> **Estado:** todo funciona en **modo sintético** (focos simulados con el formato de FIRMS). La ingesta de datos
> reales de FIRMS (Fase R del backend) sigue pendiente. La web lo indica con un aviso fijo. **No usar para decisiones.**

Análisis complementarios:
- [`docs/DESPLIEGUE_Y_FALENCIAS.md`](docs/DESPLIEGUE_Y_FALENCIAS.md): qué falla o puede fallar al publicar en internet y cómo desplegar.
- [`docs/BENEFICIOS_NASA.md`](docs/BENEFICIOS_NASA.md): qué beneficios de Space Apps sirven y para qué.

---

## 1. Estructura

```
local_plat/
├── backend/                 # motor (Python 3.12, FastAPI, DuckDB). Guía detallada: backend/README.md
│   ├── firecal/plan/        # NUEVO: capa del plan (A + C)
│   ├── api/routers/plan.py  # NUEVO: GET /api/calendario, /anomalias, /hotspots.csv, /metadatos, /departamentos
│   ├── config/regions/      # departamentos (generado con scripts/build_regions.py)
│   ├── config/regions_src/  # límites ADM1 de geoBoundaries (fuente)
│   └── tests/test_plan.py   # NUEVO: pruebas del plan
├── frontend/                # NUEVO: index.html + app.js + app.css + Leaflet 1.9.4 local (sin CDN)
├── Dockerfile               # NUEVO: imagen única API + frontend
├── docker-compose.yml
└── docs/                    # análisis de despliegue y de beneficios
```

El backend sirve el frontend en la misma dirección (`http://localhost:8000/`), así no hay problemas de CORS.

---

## 2. Procedimiento seguido (para repetirlo)

Lo que se hizo para armar esta plataforma, en orden:

1. **Clonar el backend anterior** en `local_rep` y usar la rama `backend` (en `main` solo hay un README):
   ```powershell
   git clone https://github.com/Jyron1310/project_nasa.git "C:\Nubel\local base\local_rep"
   cd "C:\Nubel\local base\local_rep"; git checkout backend
   ```
2. **Copiar** `local_rep/backend` a `local_plat/backend` y crear el entorno con Python **3.12** (no 3.13+):
   ```powershell
   cd "C:\Nubel\local base\local_plat\backend"
   py -3.12 -m venv .venv
   .\.venv\Scripts\python -m pip install --upgrade pip
   .\.venv\Scripts\python -m pip install -r requirements-lock.txt
   .\.venv\Scripts\python -m pip install -e . --no-deps
   ```
3. **Departamentos del Perú.** Se descargaron los límites ADM1 de geoBoundaries (CC BY 4.0) a
   `config/regions_src/` y se generó la región de trabajo:
   ```powershell
   .\.venv\Scripts\python scripts\build_regions.py                       # por defecto: CUS, APU, AYA, PUN, MDD
   .\.venv\Scripts\python scripts\build_regions.py PE-CUS PE-UCA PE-LOR   # otra selección
   ```
   El script imprime el `bbox` de la unión: se copió en `config/settings.yaml → region.bbox`. La región de trabajo
   (`FIRECAL_REGION`) pasó de `cusco_demo` (rectángulo) a `peru_sur` (unión de departamentos).
   Como el área es ~3,5 veces mayor, en el simulador se subió `base_per_month` (1200 → 2400) y `n_hot_zones`
   ([5, 8] → [12, 18]).
4. **Capa del plan** (`firecal/plan/`), comando `firecal plan-events`, router `/api/*` y frontend.
5. **Corrida completa y pruebas** (ver sección 3).

---

## 3. Cómo ejecutar la plataforma localmente

PowerShell, desde `C:\Nubel\local base\local_plat\backend`:

```powershell
$env:PYTHONUTF8 = "1"                                  # cada vez que abras PowerShell
.\.venv\Scripts\firecal all --mode synthetic           # ~3-4 min: simula, limpia, armoniza (B), eventos del plan (A), precálculo
.\.venv\Scripts\firecal serve                          # http://localhost:8000
```

Abre **http://localhost:8000** (la web) o **http://localhost:8000/docs** (probar la API).

- Si solo cambiaste la capa del plan: `.\.venv\Scripts\firecal plan-events` (~7 s); la API recarga los datos sola.
- Si cambiaste código de la API, reinicia `firecal serve` (`Ctrl + C` y otra vez).
- Pruebas: `.\.venv\Scripts\python -m ruff check .` y `.\.venv\Scripts\python -m pytest -q` (129 pruebas, ~1-2 min).

### Con Docker (alternativa, la misma imagen que iría a la nube)

Requiere **Docker Desktop abierto**. Desde `local_plat/`:

```powershell
docker compose up --build        # la primera vez ~3 min (instala dependencias y genera datos)
```

Verificado: la imagen `firecal-peru:local` se construye (~3 min la primera vez, ~1,5 min después) y el
contenedor responde en `http://localhost:8000`. Sin compose:
```powershell
docker build -t firecal-peru:local .
docker run --rm -p 8000:8000 firecal-peru:local
```

---

## 4. Uso de la web

1. **Área de interés:** elige un departamento (lista o clic en el mapa) o la pestaña *Dibujar rectángulo* y arrastra
   sobre el mapa (máx. 50 000 km²).
2. **Rango de fechas** (opcional para el calendario; obligatorio y de 5 años como máximo para el CSV).
3. **Color:** *Anomalía* (recomendado: compara cada mes con la mediana del mismo mes en su era de sensores) o
   *N.º de eventos* (conteo bruto, sube con VIIRS desde 2012).
4. Clic en una celda del calendario: detalle del mes con su historial y la mediana.
5. **Descargar CSV**: eventos armonizados del rango (abre bien en Excel: UTF-8 con BOM).

---

## 5. Endpoints del plan (contrato Julio ↔ Dante)

AOI en todos: `departamento=PE-CUS` **o** `bbox=oeste,sur,este,norte` **o** `lat=..&lon=..&radio_km=..`.

| Método y ruta | Parámetros | Devuelve |
| --- | --- | --- |
| `GET /api/departamentos` | — | código ISO, nombre y área de cada departamento |
| `GET /api/calendario` | AOI, `fecha_inicio`, `fecha_fin` (AAAA-MM, opcionales) | `anios`, `matriz_n_eventos`, `matriz_anomalia` (años × 12), `celdas` con `n_eventos`, `frp_total`, `mediana_hist`, `anomalia`, `categoria`, `era`, `parcial` |
| `GET /api/anomalias` | AOI, `mes` (AAAA-MM) | mes frente a la mediana y el IQR de su era + historial del mismo mes |
| `GET /api/hotspots.csv` | AOI, `fecha_inicio`, `fecha_fin` (máx. 5 años) | CSV: `fecha_utc, hora, lat, lon, celda_1km, sensor, satelite, confianza_norm, frp_mw, dia_noche, fecha_local, n_detecciones, sensores, departamento` |
| `GET /api/metadatos` | — | versión del armonizador, reglas, umbral de confianza, cobertura, conteos, créditos |

Límites (falencia 3): **429** si una IP supera 120 solicitudes/min (40 de golpe) o 10 pesadas/min; **503** si ya hay
2 consultas pesadas en curso y no se libera un turno en 2 s. Ambos traen `Retry-After`. CSV de más de 200 000 filas:
**422**. Ver `docs/DESPLIEGUE_Y_FALENCIAS.md`, sección 5.

Errores: **422** con el motivo en español (AOI vacío, departamento desconocido, rango invertido, fecha mal escrita,
área demasiado grande, rango del CSV demasiado largo); **404** sin datos; **503** si no se corrió el pipeline.
Toda respuesta trae `data_mode` y, en modo sintético, el aviso en `notes`.

Ejemplo (PowerShell):
```powershell
Invoke-RestMethod "http://localhost:8000/api/calendario?departamento=PE-CUS&fecha_inicio=2020-01&fecha_fin=2021-12"
```

Los endpoints anteriores (`POST /api/v1/...`, alternativa B en focos equivalentes a MODIS-Aqua diurno) siguen
disponibles y documentados en `backend/docs/API.md`.

---

## 6. Decisiones de método tomadas al implementar (revisar con Antonio)

1. **Un solo VIIRS a la vez.** Al sumar S-NPP + NOAA-20 + NOAA-21 la anomalía salía positiva casi todos los años
   desde 2018: más satélites dan más detecciones, no más fuego. Ahora se usa S-NPP mientras opera y NOAA-20
   después; MODIS = Terra + Aqua.
2. **Eras de sensores para la anomalía (C):** `MODIS` (ene-2003 a ene-2012) y `MODIS+VIIRS` (desde feb-2012).
   `anomalia = (n − mediana del mismo mes en la era) / max(IQR, 1)`; requiere ≥ 5 años en la era.
3. **La serie empieza en 2003-01** (Aqua completo); 2000-2002 solo tenía Terra.
4. **El mes en curso no tiene anomalía** (se vería falsamente "por debajo" por estar incompleto).
5. **Deduplicación por día local** (America/Lima), igual que los meses del calendario.
6. **Confianza normalizada:** MODIS `confidence/100`; VIIRS l/n/h = 0,3/0,6/0,9 (supuesto, ajustable). El umbral
   mínimo sigue siendo `nominal` (decisión pendiente del plan, sección 9).

Validación en modo sintético: la anomalía anual de Cusco sigue el nivel de fuego simulado (Spearman 0,86; era
VIIRS 0,94; era MODIS 0,69) y no salta en 2012, 2018 ni 2024 (prueba `test_calendario_anomaly_without_sensor_jump`).

**Limitación conocida:** A + C no corrige la deriva orbital de Terra y Aqua (cambio de hora de paso desde
~2020-2022). La alternativa B (`/api/v1`) sí la modela.

---

## 7. Pendientes

- [x] Construir y probar la imagen Docker.
- [x] Protocolo de solicitudes (falencia 3).
- [ ] Datos reales de FIRMS (Fase R): descarga del archivo histórico y NRT con MAP_KEY.
- [ ] Confirmar con el equipo los departamentos (plan, sección 9) y regenerar con `build_regions.py`.
- [ ] Fijar el umbral de confianza y el límite de latencia en ms (plan, sección 9).
- [ ] Antes de publicar: ver `docs/DESPLIEGUE_Y_FALENCIAS.md`.
