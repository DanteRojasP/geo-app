# Contrato de datos: focos FIRMS armonizados MODIS + VIIRS (Cusco, 2000-2025)

Archivo: `harmonizado_cusco_celda_dia.csv` (36 568 filas en la v1.3, una por celda de 0.01° y día local con al menos un foco).

## Columnas
| Columna | Significado |
|---|---|
| `fecha_local` | Fecha en hora de Perú (UTC−5), `YYYY-MM-DD`. Se convirtió desde `acq_date`+`acq_time` (UTC); un foco de las 02:00 UTC cae el día anterior. |
| `cell_lat`, `cell_lon` | Centro de la celda de 0.01° (~1.1 km), 3 decimales. |
| `alt_m` | Altitud SRTM media de la celda (m). |
| `n_modis` | Detecciones MODIS (Terra+Aqua) de esa celda-día. 0 si no hubo. |
| `n_viirs` | Detecciones VIIRS S-NPP de esa celda-día. 0 si no hubo. |
| `frp_modis`, `frp_viirs` | FRP total (MW) de cada sensor en la celda-día. **No son comparables entre sí** (VIIRS/MODIS ≈ ×1.2–2.0 según ambiente). |
| `eq_hotspots` | Aporte de la celda-día a la serie armonizada, en **celda-días equivalentes a MODIS (Terra+Aqua)**. |
| `fuente_serie` | `MODIS`, `Terra*kT`, `VIIRS*k`, `VIIRS-N20*k` o `MODIS-hueco`: de qué sensor sale `eq_hotspots`. En las filas `VIIRS-N20*k`, `n_viirs` y `frp_viirs` son de NOAA-20. |
| `calidad` | `referencia`, `calibrado` o `extrapolado` (ver abajo). |

## Cómo se arma `eq_hotspots` (el sensor de origen deja de importar)
| Periodo | Regla | `fuente_serie` | `calidad` |
|---|---|---|---|
| 2000-11 a 2002-07-03 (solo Terra) | 1 celda-día con Terra → `kT` | `Terra*kT` | `extrapolado` |
| 2002-07-04 a 2012-12-31 | 1 celda-día con MODIS → 1.0 | `MODIS` | `referencia` |
| 2013-01-01 en adelante | 1 celda-día con VIIRS S-NPP → `k` | `VIIRS*k` | `calibrado` |
| Días sin S-NPP en todo Perú (v1.3) | 1 celda-día con VIIRS NOAA-20 → `k20` (0.324 / 0.235) | `VIIRS-N20*k` | `calibrado` |
| Días sin S-NPP ni NOAA-20 (v1.3) | 1 celda-día con MODIS → 1.0 | `MODIS-hueco` | `referencia` |

Desde 2013 la serie se apoya en VIIRS (continuidad y mayor detalle) y se expresa en la escala de MODIS.
Factores por estrato de altitud (alto ≥ 2500 m, bajo < 2500 m):
- `k` (VIIRS→MODIS), calibrado en 2013-2019 como celda-días MODIS / celda-días VIIRS: **alto 0.330, bajo 0.247**.
- `kT` (Terra→Terra+Aqua), calibrado en 2003-2012: **alto 2.62, bajo 7.74**.

**Para agregar:** sumar `eq_hotspots` (por día, mes o región). No sumar `n_modis + n_viirs`: son sensores distintos con ~×4 de diferencia.

## Validación (ventana reservada)
- La razón VIIRS/MODIS en celda-día pasa de ×4.8 (detecciones) a ×3.9 (Perú) y ×3.0 (Cusco ≥2500 m); no llega a ×1. El sesgo es de sensibilidad, no solo de resolución, por eso se calibra.
- Calibrado en 2013-19, VIIRS×k reproduce las celda-días MODIS reales de 2020-24 con razón anual 0.90-1.09. En 2013-19 el error anual llega a ±20 % (piso de precisión del método).
- **2025:** VIIRS×k / MODIS = 1.50. MODIS cae más que VIIRS (compatible con deriva orbital de Terra/Aqua, no verificado). La serie armonizada no sufre ese efecto porque desde 2013 usa VIIRS.
- `kT` es mucho menos preciso: error mensual mediano 41-45 %, anual de −32 % a +45 % en el estrato bajo. Por eso 2000-2002 va como `extrapolado` y debe dibujarse atenuado.

## Filtros aplicados a los focos crudos
Fuente: archivos anuales por país de FIRMS (`firms.modaps.eosdis.nasa.gov/data/country/{modis|viirs-snpp}/{año}/…_Peru.csv`), 2000-2025.
- Solo `type == 0` (fuego de vegetación).
- MODIS: `confidence >= 30`. VIIRS: `confidence` en {`n`, `h`}.
- Solo S-NPP; NOAA-20 no estaba en los archivos públicos por país.
- Región: polígono de Cusco (FAO GAUL 2015 nivel 1) y altitud de SRTM a 0.01°.

## Límites a declarar en la app
- Alcance: solo Cusco. Otra región exige recalcular `k` y `kT` con sus propios estratos.
- Las "celda-días" cuentan presencia de fuego en 1 km, no área quemada ni intensidad.
- El FRP no se armoniza.

## Reproducir
1. `cusco_referencia.py` (necesita Earth Engine) genera `cusco_ref/` (límite y altitud).
2. Descargar los CSV de FIRMS a una carpeta `firms_raw/`, con los nombres que da FIRMS (`modis_AAAA_Peru.csv`, `viirs-snpp_AAAA_Peru.csv`) o renombrados (`modis_AAAA.csv`, `snpp_AAAA.csv`). Un archivo por sensor y año; si hay dos del mismo año los scripts abortan.
3. `python -I firms_csv.py firms_raw cusco_ref salida` genera el CSV y las validaciones de `kT` y de continuidad.
4. `firms_armoniza.py` (mismos argumentos) **solo imprime** diagnósticos (razón, deriva Terra/Aqua, error por calibración). No escribe ningún CSV.
5. `python -I focos_individuales.py firms_raw cusco_ref harmonizado_cusco_celda_dia.csv salida` genera `focos_cusco_individuales.csv`.
6. **v1.3:** `python -I relleno_n20.py firms_raw cusco_ref <carpeta_v1.2> salida` rellena los días sin S-NPP con NOAA-20. Necesita también los archivos `viirs-jpss1_AAAA_Peru.csv` (NOAA-20) de 2018 en adelante, y como entrada los dos CSV que dejan los pasos 3 y 5. Imprime la calibración y la validación de `k20`. Aborta si la entrada ya está rellenada.
6. `python -I verificar_datos.py harmonizado_cusco_celda_dia.csv focos_cusco_individuales.csv` valida ambos CSV (código de salida 1 si algo falla).
Variable de entorno `EE_PROJECT`: proyecto de Earth Engine para los scripts que lo usan.
