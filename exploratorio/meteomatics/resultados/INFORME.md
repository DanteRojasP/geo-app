# Clima (Meteomatics) y focos armonizados en Cusco: comparación exploratoria

*Generado por `exploratorio/meteomatics/explorar.py` · datos 2003-2025 · **exploratorio: no son
hallazgos ni pronósticos*** (MAESTRO §1.9 y `harmonizacion/sequia_fuego/PROTOCOLO.md`).

## Datos

- **Fuego:** focos armonizados de Cusco (`eq_hotspots`, MAESTRO v1.2), suma mensual, 2003-2025
  (276 meses, sin focos extrapolados).
- **Clima:** Meteomatics, un valor diario a las 18 UTC (13:00 local) en 8 puntos. Son los centros
  ponderados por fuego de las 8 celdas de 0.5° con más focos (juntas, el
  51% del fuego). El valor de Cusco es el promedio de los puntos
  ponderado por su parte del fuego. Lluvia y evapotranspiración se suman en el mes, las rachas se
  toman como máximo y el resto como media.

| punto | lat | lon | alt_m | focos | parte_del_fuego |
|---|---|---|---|---|---|
| P1 | -12.3562 | -72.8107 | 847.0 | 1799.7 | 11.9 % |
| P2 | -12.7181 | -73.2212 | 1255.0 | 1308.0 | 8.6 % |
| P3 | -12.6713 | -72.743 | 1403.0 | 1249.2 | 8.3 % |
| P4 | -12.7648 | -72.241 | 2443.0 | 989.0 | 6.5 % |
| P5 | -13.2117 | -72.7169 | 2958.0 | 662.0 | 4.4 % |
| P6 | -13.7391 | -71.76 | 3754.0 | 589.6 | 3.9 % |
| P7 | -13.2679 | -72.2721 | 3596.0 | 582.8 | 3.8 % |
| P8 | -12.9494 | -71.4127 | 640.0 | 582.2 | 3.8 % |

## Resultados (coeficiente de Spearman, rho)

Interpretación orientativa: |rho| < 0.3 débil, 0.3-0.5 moderado, > 0.5 fuerte. **Ninguno se usa
como prueba**: hay decenas de comparaciones sobre los mismos datos.

**1. Ciclo anual (12 medianas mensuales).** Es lo más claro, pero también lo más trivial: la
temporada seca coincide con la temporada de fuego.

| variable | rho | n |
|---|---|---|
| Déficit de humedad del suelo (mm) | 0.99 | 12 |
| Aviso de incendio forestal (0-1) | 0.97 | 12 |
| Humedad del suelo a 15 cm (índice) | -0.97 | 12 |
| Índice de sequía (-4 a 4) | -0.97 | 12 |
| Déficit de presión de vapor (hPa) | 0.92 | 12 |

**2. Meses de la temporada (jul-oct), quitando el ciclo estacional.** ¿Un agosto más seco de lo
normal tiene más fuego de lo normal?

| variable | rho | n |
|---|---|---|
| Lluvia (mm/mes) | -0.4 | 92 |
| Evapotranspiración (mm/mes) | 0.3 | 92 |
| Índice de Fosberg (0-100) | 0.2 | 92 |
| Déficit de presión de vapor (hPa) | 0.14 | 92 |
| Aviso de incendio forestal (0-1) | 0.13 | 92 |

**3. Años: clima medio de jul-oct frente al total de focos de jul-oct (23 años).**

| variable | rho | n |
|---|---|---|
| Lluvia (mm/mes) | -0.25 | 23 |
| Índice de sequía (-4 a 4) | -0.25 | 23 |
| Déficit de presión de vapor (hPa) | -0.22 | 23 |
| Aviso de incendio forestal (0-1) | 0.21 | 23 |
| Humedad del suelo a 15 cm (índice) | -0.19 | 23 |

**4. Años: clima de ene-jun (temporada de lluvias previa) frente al fuego de jul-oct.**

| variable | rho | n |
|---|---|---|
| Aviso de incendio forestal (0-1) | 0.26 | 23 |
| Humedad del suelo a 15 cm (índice) | -0.21 | 23 |
| Temperatura máxima (°C) | 0.2 | 23 |
| Índice de sequía (-4 a 4) | -0.18 | 23 |
| Evapotranspiración (mm/mes) | 0.17 | 23 |

**5. Rezagos: anomalía del clima de 1 a 3 meses antes frente al fuego de jul-oct.**

| variable | rho | n |
|---|---|---|
| Déficit de presión de vapor (hPa) | -0.17 | 92 |
| Índice de sequía (-4 a 4) | -0.08 | 92 |
| Lluvia (mm/mes) | 0.05 | 92 |

| variable | rho | n |
|---|---|---|
| Lluvia (mm/mes) | -0.21 | 92 |
| Índice de sequía (-4 a 4) | -0.08 | 92 |
| Humedad del suelo a 15 cm (índice) | -0.08 | 92 |

Tabla completa: `correlaciones.csv` · figuras: `perfil_estacional.png`, `anios_temporada.png`,
`correlaciones.png`.

## Límites

- **Exploratorio:** decenas de pruebas sobre los mismos 23 años. Un rho alto puede ser casualidad. Para
  confirmar algo, hay que fijar la hipótesis antes y probarla con datos nuevos (otras regiones o años),
  como pide el protocolo de `sequia_fuego/`.
- **Escala:** 8 puntos representan un departamento de ~72 000 km² con selva y puna; el fuego de
  cada punto se mide en su celda de 0.5° (~55 km).
- **Hora:** el VPD, la humedad del suelo y los índices son valores de las 13:00 local, no promedios
  diarios. Humedad relativa y viento medio no se pidieron (máximo 10 parámetros por consulta).
- **Fuente:** se desconoce el modelo o reanálisis de Meteomatics detrás de cada variable histórica;
  un cambio de modelo en la serie podría crear saltos.
- **Causalidad:** el clima puede favorecer el fuego, pero la mayoría de las quemas en Cusco son
  agrícolas o de pastos: dependen de decisiones humanas. Una correlación no lo distingue.
- **Licencia:** los datos de Meteomatics no se publican en el repositorio (solo coeficientes y
  figuras); la tabla mensual queda en `datos/` (ignorado por git).
