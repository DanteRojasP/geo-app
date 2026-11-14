# CLAUDE.md — FireCal Perú (backend)

**Antes de tocar datos o armonización, lee `MAESTRO.md` (raíz del repositorio).**

Backend local para el reto NASA Space Apps 2026 *Harmonization of MODIS and VIIRS Hot Spots*.
La especificación completa está en `C:\linasa\local_testing\PROMPT_BACKEND.md` (fuera del repo). Este archivo es su resumen.

## Reglas de trabajo
- Comunicar en **español neutro**. Código, variables y commits pueden ir en inglés; docstrings y mensajes al usuario, en español.
- El usuario es ingeniero electrónico y está empezando con backend e IA: al cerrar cada fase, resumen simple con (1) qué se hizo, (2) cómo probarlo (comandos exactos), (3) decisiones y por qué, (4) pendientes/dudas.
- **Prioridad actual: SOLO modo sintético.** Datos reales (MAP_KEY, API NRT, archivo histórico) van en la Fase R, al final.
  Meta: el sábado 14-nov el frontend debe tener la API completa respondiendo con datos sintéticos etiquetados como tales.
- Trabajar **por fases** (orden: 0, 1, 2, 3, 4, 5, 6, 7, 8, R). Al cerrar cada una: `ruff check .` y `pytest -q` en verde, commit `fase N: <resumen>`, y **detenerse a esperar el OK**.
- **Fase 4 (armonización) y Fase 7 (modelo):** mostrar el plan (fórmulas, estratos, splits) y esperar aprobación antes de escribir código.
- **No inventar** URLs, columnas de FIRMS ni funciones de librerías: verificar o dejar `TODO` y preguntar. Nunca rellenar datos faltantes con valores inventados fuera del modo sintético.
- Usar siempre `pathlib`; nada de rutas absolutas ni rutas con espacios hardcodeadas.
- Para agregar dependencias fuera de la lista permitida, pedir permiso.
- No reescribir fases aprobadas sin avisar y explicar por qué.

## Prohibido
- Subir `.env`, datos o la MAP_KEY. La MAP_KEY nunca aparece en logs (`firecal/logging_utils.py` la redacta: `.../csv/***/...`).
- Presentar datos sintéticos como reales.
- Sumar satélites VIIRS entre sí; mezclar pasadas de día y de noche en la calibración.
- Validar con división aleatoria por meses (siempre por años completos).
- PostGIS, Redis, Celery, Kubernetes o frameworks de frontend.
- Depender de la extensión `spatial` de DuckDB para algo crítico (usar H3 + shapely, prefiltro bbox en DuckDB).

## Stack
Python 3.11+ (venv local en `.venv` con **3.12**; el `py` por defecto de esta máquina es 3.15, no usarlo).
Librerías permitidas: fastapi, uvicorn[standard], pydantic>=2, pydantic-settings, duckdb, pyarrow, pandas, numpy,
h3>=4 (API v4: nombres nuevos, verificarlos), shapely>=2, pyproj, httpx, typer, pyyaml, scikit-learn, lightgbm,
matplotlib, pytest, ruff.

## Entorno
- Repo: `C:\linasa\project_nasa` (remoto GitHub del equipo), rama `backend`, código en la subcarpeta `backend/`. **No hacer push sin permiso.**
- Máquina Windows nativa (make vía `winget install ezwinports.make`). Sin make: `.venv/Scripts/python -m pytest -q`, `.venv/Scripts/python -m ruff check .`, `.venv/Scripts/firecal serve`.

## Configuración
- `.env` (ver `.env.example`): `FIRECAL_DATA_MODE` (synthetic|real, por defecto synthetic), `FIRMS_MAP_KEY`, `FIRECAL_REGION`, `FIRECAL_HOME`, `FIRECAL_CONFIG`, `FIRECAL_LOG_LEVEL`, `FIRECAL_API_HOST/PORT`.
- `config/settings.yaml`: todos los parámetros científicos (validados con Pydantic, claves desconocidas = error). Nada de números mágicos en el código.
- Acceso: `from firecal.settings import get_settings` → `.env`, `.params`, `.paths`, `.data_mode`, `.input_dir`.

## Estructura
```
config/ (settings.yaml, regions/)   firecal/ (cli, settings, logging_utils, synth, etl, grid,
api/ (main, schemas, db.Repository,             harmonization, climatology, models, regions)
      routers/, services/)          data/ (ignorado: raw/firms, synthetic, interim, processed)
models/artifacts/  reports/  docs/  tests/
```
- DuckDB en `data/processed/firecal.duckdb`. Tablas: hotspots, regions, cells, monthly_counts,
  harmonization_params, harmonized_monthly, forecasts (esquema en la sección 6 de la especificación).
- Los routers solo usan `api.db.Repository` (para poder migrar a PostGIS después).
- Toda respuesta JSON incluye `data_mode`, `data_version`, `generated_at` y `notes`.

## Notas para fases futuras
- **Fase 4:** `aqua_observed_until` = "2021-06" (= fin de `calib_window`). El plan de la Fase 4 debe incluir un
  análisis de la razón Aqua/S-NPP por año (2012–2025) para fijar el corte con datos reales. En modo sintético ese
  análisis solo se reporta (la deriva la simulamos nosotros), no se usa para decidir.
- **Fase 6:** el CSV de `/hotspots` se escribe en **utf-8-sig** (con BOM) para que Excel en Windows muestre bien las tildes.
- **Fase 6:** AOI tipo `region` exenta de `max_aoi_km2` SOLO en `/calendar`, `/anomaly` y `/map/cells`. `/hotspots` mantiene
  `max_csv_years` incluso para regiones.
- **Fase 6:** en los JSON la banda se llama `band_p10` / `band_p90`; calcularla para el AOI al consultar con
  `harmonization_bootstrap` (Σ_s R_s^b x V_s por réplica) + `harmonization_band_error` si `applied`
  (`firecal.harmonization.band`). `/meta` debe describir qué representa la banda y que la unidad son focos equivalentes a
  Aqua **DIURNO** (las nocturnas no entran al calendario).

## Simulador (Fase 1)
- `firecal synth` -> `data/synthetic/`: un CSV por sensor-satélite-año UTC-versión (`modis_aqua_2010_syn.csv`,
  `viirs_n20_2026_syn-nrt.csv`), con las columnas exactas de FIRMS. Los NRT no traen `type`.
- `truth.parquet`: por (year, month local, satellite, daynight): `expected`, `expected_nodrift` (lo que se vería con la
  hora de paso nominal, sin deriva orbital: referencia para validar la armonización), `n_vegetation`, `n_industrial`,
  `n_bowtie`, `n_total`.
  `truth_events.parquet`: un evento por fila. `manifest.json`: parámetros, zonas, años extremos, fuentes industriales.
- Parámetros en `settings.yaml` -> `synthetic`. Solo las columnas radiométricas (brillo, FRP, scan/track) usan
  coeficientes cosméticos en `_COSMETIC` (generator.py); el pipeline no las usa.
- Flujos aleatorios separados (paisaje / eventos / detección / ruido): cambiar la detección no cambia los eventos.
- Deriva orbital = cambio de la HORA de paso (`overpass_drift`, nodos con interpolación lineal); el efecto sale del
  ciclo diurno. Con los valores actuales: Aqua +3-4 % (se acerca al pico de 15:00), Terra hasta -20 % en 2026.
- Las detecciones de un fuego en una pasada ocupan píxeles vecinos de una rejilla scan x track (>= 1 píxel entre sí),
  como en datos reales; así el filtro bow-tie (< 1 km) no quita detecciones legítimas.
- Códigos de satélite sintéticos: Terra, Aqua, N, N20, N21 (ver Fase R).
- Rendimiento con scale=1: ~1.3 M filas, ~10–20 s, ~120 MB.

## Ingesta y limpieza (Fase 2)
- `firecal ingest` -> tabla `hotspots_raw` (normalizada). Lee la carpeta del modo actual: `data/synthetic/` (synthetic)
  o `data/raw/firms/` (real); **nunca mezcla ambas**. Esquema MODIS/VIIRS detectado por columnas.
- `firecal build --step clean` -> tabla `hotspots` (con `px1km_id`, `is_static`; `h3_7` se llena en la Fase 3) y vista
  `hotspots_clean` (= `NOT is_static`: lo que usan todos los cálculos posteriores). Reporte en `reports/clean_summary.json`.
- Orden de limpieza: duplicados -> NRT cubierto por SP -> bow-tie MODIS -> región+buffer (UTM) -> marca de fuentes fijas
  (con todas las filas, incluidas `type != 0`, para que también se marquen en el periodo NRT) -> `type != 0` -> confianza.
- Supuestos sobre el formato real de FIRMS: **solo** en `firecal/etl/firms_schema.py` (`FIRMS_ASSUMPTIONS`, TODO-REAL).
- `firecal ingest --source nrt` y `firecal/etl/nrt_fetch.py`: pendientes (Fase R). Nada de red en los tests.
- Región de trabajo: `peru_sur` = unión de los departamentos de `config/regions/peru_departamentos.geojson`
  (geoBoundaries ADM1, generado con `scripts/build_regions.py`; reemplazó a `cusco_demo`).
- Test `tests/test_ascii_messages.py`: logs, `typer.echo` y excepciones deben ser ASCII.

## Agregación (Fase 3)
- `firecal build --step aggregate`: llena `hotspots.h3_7` y crea `regions`, `cells` (universo de celdas res 7: las de las
  regiones + las que tienen focos; `parent_calib` res 4; `region_codes` VARCHAR[]; `lat`/`lon` del centro),
  `monthly_counts` (mes LOCAL; solo `hotspots_clean`) y `satellite_coverage` (primer/último mes y desde cuándo hay NRT).
- Tablas dispersas: (celda, mes, satélite) sin focos no tiene fila = 0 focos, si el satélite operaba ese mes
  (ver `satellite_coverage`). `is_provisional` = ese satélite tiene NRT en ese mes.

## Armonización (Fase 4)
- `firecal build --step harmonize` -> `harmonization_params`, `harmonization_bootstrap` (pair, estrato, rep, ratio),
  `harmonization_band_error`, `harmonized_months` (fuente por mes) y `harmonized_monthly` (h3, year, month, value,
  p10, p90, raw_value, source, satellite, pair, estrato, low_confidence, is_provisional, version).
  `firecal validate` -> `reports/harmonization_metrics.json` + PNG. Método en `docs/METODOLOGIA.md`.
- Pares: SNPP->AQUA, N20->SNPP, N21->SNPP, TERRA->AQUA; compuestos N20->AQUA, N21->AQUA (réplicas multiplicadas).
- Estratos: padre res 4 x temporada -> res 3 x temporada -> regional (umbrales en el YAML).
- Hallazgo (sintético): meses tranquilos sobreestimados +15-24 % a nivel regional (documentado, no corregido).
- Banda: factor (bootstrap) + error dependiente del tamaño del conteo PREDICHO (rangos `band_error_pred_edges`),
  estimado por leave-one-year-out en `calib_window` sin 2019-2020; cobertura fuera de muestra 75-89 % (meta 70-90 %).
  Para un AOI se usa el conteo predicho del AOI completo.
- `reliability` (alta/media/baja) por conteo anual esperado del AOI (`settings.yaml -> reliability`, 25 y 100
  focos/año); en `/calendar` y `/anomaly`; si es "baja", agregar nota.
- DuckDB 2: no usar `fetchone()` (deja el resultado abierto y rompe `register`); usar `fetchall()[0]`.

## API (Fase 6)
- `api/db.py::Repository`: carga en memoria (h3 categórica para filtros rápidos) y recarga si cambia el archivo
  DuckDB; no deja conexiones abiertas (Windows bloquea el archivo). `/hotspots` consulta DuckDB (bbox + fechas).
- Servicios en `api/services/` (common: AOI y envoltura; series: calendar/anomaly; other: hotspots, map, regions,
  meta, forecast; cache: precompute). Routers delgados en `api/routers/`. Dependencia `api.deps.RepoDep`.
- `data_mode` de las respuestas = el grabado por el pipeline en `pipeline_info` (no el .env); si difieren, nota.
- JSON con `charset=utf-8` explícito (PowerShell 5.1). Errores 422 en español (`AOIError`), 503 sin datos.
- `/forecast` devuelve `available: false` hasta la Fase 7 (lee `models/artifacts/metadata.json` -> `forecasts`).
- `firecal all --mode synthetic` (~200 s con 5 departamentos) y `firecal precompute` (caché por región en `data/processed/cache/`).

## Codificación y Windows
- Todo en UTF-8: `PYTHONUTF8=1` (Makefile y `.env.example`; en PowerShell sin make: `$env:PYTHONUTF8 = "1"`).
  `firecal.logging_utils.force_utf8_stdio()` reconfigura stdout/stderr a UTF-8 al importar la CLI.
- Mensajes de consola en ASCII como medida extra (sin flechas ni símbolos), pero sin depender de ello.
- `.gitattributes` fija LF para Makefile, Dockerfile, *.sh, *.py, *.yaml, *.md, *.toml.
- El usuario sigue en **Windows nativo + PowerShell** (no WSL2) durante el hackathon: todo debe funcionar ahí.

## Capa del plan: datos reales de Cusco (desde 14-nov)
- Fuente: CSV de Antonio en `<repo>/data/harmonized/` y `<repo>/harmonizacion/cusco_ref/` (`firecal/plan/sources.py`;
  `FIRECAL_SOURCE_ROOT` cambia la raíz). Contrato y sumas de control de MAESTRO §6 en `sources.CONTROL`.
- `firecal plan-events` -> valida (columnas, filas, sumas, SHA-256) y escribe `data/processed/plan/{celda_dia,focos}/anio=/mes=`
  + `cusco_limite.geojson` + `plan_meta.json`. Falla si los datos no coinciden (DataContractError).
- Reglas del equipo (MAESTRO §1 y §12): solo Cusco; unidad "focos armonizados" = Σ eq_hotspots / Σ eq_foco; no contar
  filas; no usar FRP; no usar la palabra "evento"; fuera de cobertura = "sin datos" (404), nunca 0.
- `firecal.plan.query.PlanStore`: departamento -> tabla celda-día; bbox/punto -> focos por latitude/longitude (el total
  coincide con la descarga). Anomalía C sobre meses referencia/calibrado.
- `/api/v1` (sintético) apagado: `api.legacy_v1: false`. Los tests del backend anterior lo activan en `pipeline_home`.
- Tests: `tests/test_plan.py` (fixture `plan_home`, casos de MAESTRO §12) y `tests/test_limits.py`.

## Estado de fases
- [x] Fase 0 — andamiaje
- [x] Fase 1 — simulador (con ajustes: deriva por hora de paso, detecciones en rejilla de píxeles)
- [x] Fase 2 — ingesta y limpieza (reducida: solo CSV locales; NRT pendiente)
- [x] Fase 3 — agregación
- [x] Fase 4 — armonización (plan aprobado con correcciones)
- [x] Fase 5 — climatología, anomalía y percentiles (`firecal/climatology/`: aoi, climatology, percentiles, anomaly)
- [x] Fase 6 — API completa en modo sintético (contratos en `docs/API.md`)
- [ ] Fase 7 — modelo predictivo (**plan primero**)
- [ ] Fase 8 — empaquetado y documentación
- [ ] Fase R — datos reales (al final o después del hackathon)

## Fase R — datos reales: TODO-REAL pendientes
Supuestos de formato (todos en `firecal/etl/firms_schema.py::FIRMS_ASSUMPTIONS`):
- [ ] Códigos de la columna `satellite` en CSV reales (SP y NRT) de MODIS, S-NPP, NOAA-20 y NOAA-21.
- [ ] `acq_time`: confirmar que es HHMM en UTC y su formato (con/sin ceros a la izquierda; ya se aceptan ambos).
- [ ] Valores de `version` en SP y NRT (se asume: contiene "NRT" -> NRT; si no -> SP).
- [ ] Confianza VIIRS en NRT (¿l/n/h o palabras completas?) y valores de `daynight`.
- [ ] Presencia de `type` en los archivos SP descargados.
Ingesta:
- [ ] Implementar `firecal/etl/nrt_fetch.py` (API `area`: máximo de días por solicitud, límite de transacciones, backoff,
      respuestas crudas en `data/raw/firms/nrt/`, MAP_KEY redactada) y `firecal ingest --source nrt`.
- [ ] Probar la regla "SP reemplaza a NRT" (por hora del último SP de cada satélite) con datos reales solapados.
- [ ] Revisar `static_source_month_fraction` con fuentes fijas reales (minas, industrias) de la región.
Geografía y ciencia:
- [ ] Reemplazar la región demo (rectángulo) por límites reales (departamento/provincias de Cusco) en `config/regions/`.
- [ ] Análisis de la razón Aqua/S-NPP por año (2012–2025) para fijar `aqua_observed_until` (ver notas de la Fase 4).
- [ ] Recalibrar y validar la armonización con datos reales; comparar con el rango publicado (S-NPP ≈ 3.9–6.8× Aqua).

## Experimento opcional (solo si sobra tiempo DESPUÉS de la Fase 6)
Corregir el sesgo de meses tranquilos (+15-24 % regional; documentado en `docs/METODOLOGIA.md` 3.3): reemplazar
"temporada" en el estrato por una **clase de actividad esperada de 2 niveles** (alta/baja), según la climatología de VIIRS
por celda padre y mes del año, calculada SOLO con años de calibración. Mantiene la aditividad (sigue siendo un factor
por celda-mes). Comparar con las métricas actuales (sesgo por tercil, cobertura) antes de adoptarlo.
