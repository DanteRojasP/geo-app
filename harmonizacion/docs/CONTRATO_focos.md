# Focos individuales FIRMS de Cusco con peso armonizado (2000-2025)

Archivo: `focos_cusco_individuales.csv`. Una fila por foco (MODIS Terra/Aqua y VIIRS S-NPP) que pasa los filtros del proyecto, con el peso que aporta a la serie armonizada.
Sumar `eq_foco` en cualquier región y fechas reproduce `eq_hotspots` de `harmonizado_cusco_celda_dia.csv` (mismo cálculo, repartido entre los focos de cada celda-día).

## Columnas
| Columna | Significado |
|---|---|
| `fecha_local`, `fecha_utc`, `hora_utc` | Fecha de Perú (UTC−5), y fecha y hora UTC originales del foco (`HHMM`). |
| `latitude`, `longitude` | Posición original del foco (FIRMS). |
| `cell_lat`, `cell_lon` | Centro de la celda de 0.01° (~1.1 km) a la que se asigna. |
| `alt_m` | Altitud SRTM de la celda (m). |
| `sensor` | `MODIS` o `VIIRS`. |
| `satelite` | `Terra`, `Aqua`, `Suomi-NPP` o `NOAA-20` (este último solo en los días sin S-NPP, v1.3). |
| `frp` | Potencia radiativa del foco (MW), sin armonizar. No comparable entre sensores (VIIRS/MODIS ≈ ×1.2-2.0). |
| `brillo_k` | Temperatura de brillo (K): banda T21 en MODIS, I4 en VIIRS. |
| `confianza` | Confianza original de FIRMS (0-100 en MODIS; `n`/`h` en VIIRS). |
| `diurno_nocturno` | `D` o `N`. |
| `en_serie` | 1 si el foco lleva peso en la serie armonizada; 0 si se conserva solo como registro. |
| `eq_foco` | Aporte del foco en celda-días equivalentes a MODIS (0 si `en_serie` = 0). |
| `fuente_serie` | `MODIS`, `Terra*kT`, `VIIRS*k`, `VIIRS-N20*k`, `MODIS-hueco` o `fuera_de_serie`. |
| `calidad` | `referencia`, `calibrado`, `extrapolado` o vacío (fuera de serie). |

## Reglas de peso
- 2002-07-04 a 2012: lo llevan los focos MODIS de la celda-día; entre todos suman 1.0.
- 2013 en adelante: lo llevan los focos VIIRS; entre todos suman `k` (0.330 sobre 2500 m, 0.247 debajo). Los focos MODIS de esos años quedan con `en_serie` = 0.
- 2000 a 2002-07-03 (solo Terra): lo llevan los focos Terra; suman `kT` (2.62 sobre 2500 m, 7.74 debajo). `calidad` = `extrapolado`.
- Los focos VIIRS de 2012 quedan fuera de la serie (`en_serie` = 0), porque la serie usa MODIS hasta fin de 2012.

## Filtros
Solo `type == 0` (vegetación). MODIS con `confidence >= 30`; VIIRS con `n` o `h`. Región: polígono de Cusco (FAO GAUL). Fuente: archivos anuales por país de FIRMS.

## Qué no es
Un foco no mide área quemada ni intensidad del incendio: es un píxel con anomalía térmica en el momento del paso del satélite. Para agregar, sumar `eq_foco`, no contar filas.
