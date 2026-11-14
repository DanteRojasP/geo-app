# API de FireCal Perú — contratos para el frontend

Base: `http://localhost:8000` · Documentación interactiva: `http://localhost:8000/docs`
CORS habilitado para `http://localhost:5173` y `http://localhost:3000` (`api.cors_origins` en
`config/settings.yaml`).

> **Modo actual: `synthetic`.** Toda respuesta trae `data_mode`. Mientras sea `"synthetic"`, los
> datos son simulados: muéstralo en la interfaz (p. ej. una cinta "DATOS SIMULADOS").

## Convenciones

**Campos presentes en toda respuesta JSON**

| Campo | Tipo | Descripción |
| --- | --- | --- |
| `data_mode` | `"synthetic"` \| `"real"` | Origen de los datos (lo graba el pipeline). |
| `data_version` | string | Versión de la armonización, p. ej. `"harm-v0.1"`. |
| `generated_at` | ISO 8601 UTC | Momento de la respuesta. |
| `notes` | string[] | Avisos para mostrar al usuario (sintético, meses provisionales, confiabilidad baja, etc.). |

**Unidad del calendario armonizado:** focos equivalentes a MODIS-Aqua **diurno** por mes (hora
local de Lima). Las detecciones nocturnas no entran. Es "actividad de quema detectable", no número de
incendios.

**Banda `band_p10` / `band_p90`:** intervalo 10–90 % del valor. Combina la incertidumbre del factor
de conversión VIIRS→Aqua y el error observado de la conversión (que depende del tamaño del conteo).
En meses observados directamente por Aqua (`source = "modis_observed"`) la banda es igual al valor.

**Confiabilidad `reliability`** (`/calendar`, `/anomaly`): `"alta"` | `"media"` | `"baja"` según el
conteo anual esperado del AOI (< 25 → baja; ≥ 100 → alta). Si es `"baja"`, hay un aviso en `notes`.

**Errores:** `422` con `{"detail": "<mensaje en español>"}` (validación del AOI, fechas, etc.).
Errores de esquema: `{"detail": "Solicitud inválida…", "errors": [{"campo", "error"}]}`.
`503` si el pipeline no se ha corrido (`{"detail": "No existe la base de datos…"}`).

## AOI (área de interés)

Un solo objeto con discriminador `type`:

```json
{"type": "region", "code": "PE-CUS"}
{"type": "bbox", "bbox": [-72.6, -13.8, -71.8, -13.2]}          // [oeste, sur, este, norte]
{"type": "point", "lat": -13.5, "lon": -72.0, "radius_km": 25}  // radius_km <= 100
{"type": "geojson", "geometry": {"type": "Polygon", "coordinates": [[[lon, lat], ...]]}}
```

- WGS84 (lon, lat). `geojson` solo Polygon o MultiPolygon, geometría válida (si no: 422).
- Área máxima `50 000 km²`. Las AOI `region` están exentas en `/calendar`, `/anomaly` y
  `/map/cells`, **no** en `/hotspots`.
- El AOI se aproxima con celdas H3 res 7 (~5 km²) cuyo centro cae dentro; en `/hotspots` el filtro
  es exacto (punto en polígono). `aoi` en la respuesta: `{type, area_km2, n_cells, region_code}`.

## Endpoints

### `GET /health`
`{"status": "ok", "data_mode": "synthetic", "data_ready": true}` — `data_ready=false` si falta
correr el pipeline.

### `GET /api/v1/regions`
GeoJSON `FeatureCollection` (geometría simplificada) + campos comunes. `properties`:
`code`, `name`, `level`, `area_km2`, `n_cells`. Hoy: `peru_sur` (unión, level `conjunto`) y los departamentos `PE-CUS`, `PE-APU`, `PE-AYA`, `PE-PUN`, `PE-MDD` (level `departamento`).

### `POST /api/v1/calendar`
Matriz año × mes para el heatmap de ECharts.

```json
{"aoi": {...}, "mode": "harmonized", "start_year": 2003, "end_year": 2026}
```

| `mode` | `value` |
| --- | --- |
| `harmonized` (defecto) | focos equivalentes Aqua diurno, con banda |
| `percentile` | percentil 0–100 del conteo crudo en la climatología de su propio satélite (independiente del sensor) |
| `raw_modis` | focos crudos Aqua diurno (sin armonizar; Aqua deriva desde ~2021) |
| `raw_viirs` | focos crudos VIIRS diurno, un satélite por mes (S-NPP, N20 o N21), sin armonizar |

`start_year` por defecto 2003 (`series_start`); se puede pedir desde 2000 (meses 2000-11 a 2002-07
con `low_confidence: true`). Respuesta (recortada, datos sintéticos):

```json
{
  "data_mode": "synthetic", "data_version": "harm-v0.1", "generated_at": "2026-11-12T20:03:44+00:00",
  "notes": ["Datos sintéticos: no usar para decisiones.", "Bordes del AOI aproximados por celdas H3 (res 7, ~5 km²).",
            "Solo pasadas diurnas: las detecciones nocturnas no entran al calendario.", "…",
            "Meses provisionales (NRT): pueden cambiar cuando lleguen los datos definitivos."],
  "unit": "focos equivalentes MODIS-Aqua (diurno)",
  "mode": "harmonized",
  "years": [2026], "months": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
  "cells": [
    {"year": 2026, "month": 8, "value": 12.386, "band_p10": 7.444, "band_p90": 17.426, "percentile": 15.0,
     "source": "viirs_converted", "satellite": "SNPP", "provisional": true, "low_confidence": false},
    {"year": 2026, "month": 11, "value": 1.616, "band_p10": 0.376, "band_p90": 3.832, "percentile": 25.0,
     "source": "viirs_converted", "satellite": "N20", "provisional": true, "low_confidence": false}
  ],
  "climatology": [{"month": 8, "median": 19.5, "p25": 13.775, "p75": 25.25, "p90": 31.2, "n_years": 20}],
  "aoi": {"type": "bbox", "area_km2": 5749.4, "n_cells": 990, "region_code": null},
  "reliability": "media",
  "expected_annual": 81.7
}
```

- `cells` solo trae meses con fuente (en `raw_modis` no hay meses antes de Aqua, etc.); un mes
  ausente en `cells` = sin dato (no 0).
- `source`: `modis_observed` | `viirs_converted` | `terra_adjusted` (modos armonizado/percentil);
  `aqua_raw`, `snpp_raw`, `n20_raw`, `n21_raw` (modos crudos).
- `percentile`: posición del mes en la climatología 2003–2022 de su mes del año.
- `climatology`: mediana, p25, p75, p90 por mes del año (`climatology.base_years`).
- La consulta por defecto de cada región (`{"aoi": {"type": "region", …}}`) se sirve precalculada
  si se corrió `firecal precompute`.

### `POST /api/v1/anomaly`
```json
{"aoi": {...}, "year": 2025, "month": 9}     // year+month opcionales (juntos): defecto = último mes
```
```json
{
  "...campos comunes...": "", "unit": "focos equivalentes MODIS-Aqua (diurno)",
  "aoi": {"type": "bbox", "area_km2": 5749.4, "n_cells": 990, "region_code": null},
  "reliability": "media", "expected_annual": 81.7,
  "year": 2025, "month": 9, "value": 17.564, "band_p10": 10.688, "band_p90": 24.608,
  "median": 15.767, "p25": 12.75, "p75": 19.5, "p90": 28.1, "n_years": 20,
  "anomaly_abs": 1.797, "anomaly_pct": 11.398,
  "percentile": 55.0, "percentile_sensor": 45.5, "category": "normal",
  "source": "viirs_converted", "satellite": "SNPP", "provisional": false, "low_confidence": false
}
```
`category`: `muy por debajo` (< p10) · `por debajo` (< p25) · `normal` · `por encima` (> p75) ·
`muy por encima` (> p90). `percentile_sensor`: percentil independiente del sensor.

### `POST /api/v1/hotspots`
```json
{"aoi": {...}, "start": "2025-08-01", "end": "2025-09-30", "format": "csv"}   // o "geojson"
```
- Fechas locales (America/Lima), inclusivas; rango máximo 5 años (también para regiones).
- Focos limpios (sin fuentes fijas, confianza ≥ nominal, solo vegetación), día y noche.
- **CSV** (defecto): streaming, UTF-8 con BOM (Excel en Windows muestra bien las tildes),
  `Content-Disposition: attachment`, cabeceras `X-Data-Mode` y `X-Row-Count`. Columnas:
  `id, sensor, satellite, acq_utc, local_date, lat, lon, confidence_cat, confidence_raw, frp,
  daynight, type, version, h3_7, data_mode`. Si Excel muestra todo en una columna (separador de
  lista `;` en la configuración regional), usar *Datos → Desde texto/CSV*.
- **GeoJSON**: `FeatureCollection` de puntos (máx. 50 000; si no, 422 sugiriendo CSV).

### `POST /api/v1/map/cells`
```json
{"aoi": {...}, "year": 2025, "month": 9}
```
GeoJSON de hexágonos H3 con `value > 0` en ese mes (las demás celdas valen 0) + campos comunes,
`unit`, `year`, `month`, `source`, `satellite`, `provisional`, `aoi`, `n_cells_with_data`.
`properties`: `h3`, `value`, `p10`, `p90` (incertidumbre del factor por celda), `raw_value`.

### `POST /api/v1/forecast`
```json
{"region_code": "PE-CUS"}
```
Hasta la Fase 7 responde `200` con `"available": false` y un aviso en `notes`. Después:
`target_year`, `target_month`, `prob_above_median`, `expected_value`, `skill`,
`beats_climatology`, `model_version`.

### `GET /api/v1/meta`
Unidad (`unit`, `unit_description`), descripción de la banda (`band_description`),
`last_update`, rango de la serie y meses por fuente, años de climatología, cobertura por satélite,
razones regionales de armonización, resumen de validación (sesgo y cobertura de banda por cadena),
umbrales de confiabilidad, límites y regiones disponibles.

## Cómo levantarla

```powershell
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\firecal all --mode synthetic   # ~1-2 min: datos sintéticos + pipeline + caché
.\.venv\Scripts\firecal serve                   # http://localhost:8000/docs
```


---

## Endpoints del plan (GET /api/*)

Desde el 14-nov sirven los **datos reales de Cusco** (MAESTRO.md) y la documentación vigente está en
[`../../README.md`](../../README.md), sección 4. Resumen:

| Ruta | Respuesta principal |
| --- | --- |
| `GET /api/departamentos` | `departamentos: [{code: "PE-CUS", ...}]`, `geojson` (límite FAO GAUL) |
| `GET /api/calendario` | `matriz_focos_armonizados`, `matriz_anomalia`, `total_focos_armonizados`, `cortes_color`, `celdas[]` (con `rango` e `incertidumbre`) |
| `GET /api/anomalias` | `focos_armonizados`, `rango`, `mediana_hist`, `anomalia`, `categoria`, `calidad`, `historial[]`, `dias[]` |
| `GET /api/focos.geojson` | focos como puntos para el mapa (`eq_foco`, sensor, fecha, calidad) |
| `GET /api/hotspots.csv` | CSV con las 18 columnas del contrato de focos (`harmonizacion/docs/CONTRATO_focos.md`) |
| `GET /api/metadatos` | unidad, factores k y kT, calidad, cobertura, sumas de control, créditos |

Los endpoints `/api/v1/*` de este documento son del backend anterior (sintético) y están apagados por defecto.
