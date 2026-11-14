# Metodología — FireCal Perú

> Estado: modo **sintético**. Todas las cifras de este documento salen de datos simulados y solo
> sirven para verificar que el método funciona. No describen la actividad de fuego real.

## 1. Qué mide el calendario

El calendario muestra **focos equivalentes a MODIS-Aqua DIURNO** por mes (hora local de Lima).

- Solo entran las **pasadas diurnas** (`daynight = D`). Las detecciones nocturnas se descargan y se
  guardan, pero **no entran al calendario armonizado**.
- Es "actividad de quema detectable por satélite", no número de incendios. En zonas altoandinas los
  satélites omiten la mayoría de quemas pequeñas.
- Antes de agregar, se limpian los focos: duplicados, NRT reemplazado por SP, duplicados *bow-tie*
  de MODIS, recorte a la región + 3 km, fuentes fijas (celdas de ~1 km con focos en más del 40 % de
  los meses), `type != 0` y confianza baja.

## 2. Armonización

### 2.1 Fuente de cada mes

| Periodo | Fuente | `source` | Notas |
| --- | --- | --- | --- |
| 2000-11 a 2002-07 | Terra D × R(TERRA→AQUA) | `terra_adjusted` | `low_confidence` |
| 2002-08 a `aqua_observed_until` (2021-06) | Aqua D observado | `modis_observed` | sin conversión |
| 2021-07 a 2026-10 | S-NPP D × R(SNPP→AQUA) | `viirs_converted` | |
| 2026-11 en adelante | N20 D × R(N20→SNPP) × R(SNPP→AQUA) | `viirs_converted` | S-NPP dejó de producir datos el 2026-11-02 |
| (respaldo) | N21 D × R(N21→SNPP) × R(SNPP→AQUA) | `viirs_converted` | solo si falta N20; `low_confidence` |

Un satélite solo se usa en meses que operó **completos** (periodos en
`harmonization.satellite_periods`). El calendario empieza por defecto en `series_start` (2003-01);
2000–2002 existe pero con baja confianza.

`aqua_observed_until` = 2021-06 porque Aqua y Terra derivan de su órbita desde ~2021: su hora de
paso cambia y con ella la fracción de fuegos que ven (ciclo diurno). Con datos reales, este corte se
revisará con la razón Aqua/S-NPP por año (2012–2025); en modo sintético esa razón solo se reporta.

### 2.2 Razón de sumas por estrato (método principal)

Para un par fuente → referencia, en los meses elegibles (completos para ambos satélites, sin datos
provisionales):

    R_s = Σ focos de referencia en el estrato s / Σ focos de la fuente en el estrato s
    valor convertido de una celda = R_s × focos de la fuente en la celda

- **Estrato** = celda padre H3 res 4 × temporada (seca = meses 5–10; húmeda = resto).
- **Fusión**: si un estrato no tiene ≥ 200 focos de la referencia o datos en ≥ 5 años, usa su celda
  padre res 3 × temporada; si tampoco, el estrato regional de su temporada. Celdas nunca vistas en la
  calibración usan el regional.
- **Por qué razón de sumas:** es *aditiva*. Convertir celda por celda y sumar da lo mismo que sumar
  y convertir, así el calendario de cualquier área (AOI) es coherente con el de sus partes.
- **Ventanas:** SNPP→AQUA 2012-02..2021-06; N20→SNPP 2018-04..2026-10; N21→SNPP 2024-02..2026-10;
  TERRA→AQUA 2003..2019 (sin 2020: la deriva de Terra empieza ahí).
- Los parámetros de producción se ajustan con **todos** los años de cada ventana; la validación usa
  un ajuste aparte sin los años reservados.

### 2.3 Banda `band_p10` / `band_p90`

1. **Incertidumbre del factor** (bootstrap por bloques de años, B = 1000): se remuestrean años
   completos con reemplazo y se recalcula cada R_s. Las réplicas se guardan
   (`harmonization_bootstrap`). Para un AOI, en cada réplica b se calcula
   `Σ_s R_s^b × V_s` (V_s = focos de la fuente del AOI en el estrato s) y se toman los cuantiles
   10 % y 90 %. Esto mide **cuánto podría variar el factor**, no cuánto se equivoca un mes concreto.
2. **Error observado, dependiente del tamaño.** La banda del factor cubre muy pocos meses (ver
   3.3): el ruido de conteo de cada mes es mucho mayor que la incertidumbre del factor. Como su
   cobertura es menor que 0.70, se agrega el error observado:

       e = log((obs + 1) / (pred + 1))
       band_p10 = max(0, (factor_p10 + 1) · exp(q10(e | pred)) − 1)
       band_p90 =        (factor_p90 + 1) · exp(q90(e | pred)) − 1

   - q10(e | pred), q90(e | pred) son cuantiles empíricos de e agrupados por **rangos del conteo
     predicho** (`band_error_pred_edges`: 0–2, 2–8, 8–30, 30–120, ≥ 120). El error relativo se
     achica con el tamaño (como el ruido de Poisson): ±60 % para 0–2 focos, ±7 % para ≥ 120.
   - Se estima con **leave-one-year-out dentro de `calib_window`, SIN 2019–2020**: para cada año se
     calibra con los demás y se predice ese año (unidades celda padre-mes y región-mes).
   - Para un AOI se usa el **conteo predicho del AOI completo** (no celda por celda).
   - Las cadenas N20 y N21 usan el error de S-NPP (N20 y Aqua casi no se solapan fuera de 2019–2020;
     N21 no se solapa con Aqua). Terra usa su propio leave-one-year-out (2003–2018).
   - Tabla `harmonization_band_error`.
3. Meses `modis_observed`: banda = valor (dato observado, sin conversión).

La cobertura se mide **fuera de muestra** en 2019–2020; meta 70–90 % (ver 3.3).

### 2.5 Confiabilidad de un AOI (`reliability`)

`/calendar` y `/anomaly` informan `reliability` = `alta` / `media` / `baja` según el **conteo anual
esperado** del AOI (media de los totales anuales armonizados en `climatology.base_years`):

| Conteo anual esperado | `reliability` | Error relativo mensual típico (celdas padre, 2019–2020) |
| --- | --- | --- |
| < 25 | baja | > ~50 % (mediana 57–91 %) |
| 25 – 100 | media | ~30–45 % |
| ≥ 100 | alta | < ~25 % (mediana 18–21 %) |

Los umbrales están en `settings.yaml → reliability` y la curva que los justifica en
`harmonization_metrics.json → reliability_curve`. Si es `baja`, la API agrega un aviso en `notes`.

### 2.4 Método de contraste

Regresión `log1p(Aqua) ~ log1p(S-NPP)` (y variante con `log1p(píxeles ~1 km)`) sobre la serie
regional mensual, con corrección de *smearing* de Duan. Solo para comparar en el reporte: no es
aditiva, así que no sirve para AOI arbitrarios.

**Con solo 24 meses reservados, las diferencias entre el método principal y el de contraste no son
estadísticamente significativas** (MAE relativo 5.0 % frente a 5.2–5.5 %; sesgos +1.1 % frente a
+1.3–1.6 %). La razón de sumas se elige por ser **aditiva** (coherencia de cualquier AOI con sus
partes), no por ser más precisa.

## 3. Validación (años reservados 2019–2020)

Se calibra sin 2019–2020 y se predice Aqua diurno en esos años. Reporte completo en
`reports/harmonization_metrics.json` y gráficos en `reports/*.png`.

### 3.1 Criterio de aceptación
|sesgo relativo regional| < 15 % para S-NPP → Aqua. Es un criterio débil (la razón de sumas lo
cumple casi por construcción), por eso se reportan además:

### 3.2 Métricas adicionales
- Por celda padre res 4 (con ≥ 50 focos observados): mediana y peor caso de sesgo, error relativo,
  Spearman y coincidencia de los 3 meses más activos.
- Sesgo por nivel de actividad **esperado** del mes (terciles). El nivel es la media de Aqua en ese
  mes del año y celda padre en años no reservados; clasificar por el valor observado del propio mes
  sesgaría el resultado (regresión a la media).
- Cadena N20 → S-NPP → Aqua por separado (es la conversión que se usa desde nov-2026).
- Cobertura de la banda del factor y de la banda ensanchada.

### 3.3 Resultados en modo sintético (resumen)
- Sesgo regional en años reservados: S-NPP→Aqua +1.1 %, N20→S-NPP→Aqua +1.6 %, Terra→Aqua −1.5 %.
- **Sesgo conocido, no corregido: los meses tranquilos se sobreestiman.** Tercil bajo de
  actividad esperada: +15 % (S-NPP), +24 % (N20) y +20 % (Terra) a nivel regional; +4 a +17 % por
  celda padre. La razón de sumas queda dominada por los meses de mucho fuego, donde los fuegos son
  más grandes y la razón Aqua/VIIRS es distinta; la temporada (seca/húmeda) del estrato solo lo
  corrige en parte. Efecto práctico: en meses de poca actividad el calendario armonizado tiende a
  mostrar algo más de lo que Aqua habría visto. En valores absolutos el efecto es chico (son meses
  con pocos focos) y no afecta la identificación de los meses de mayor actividad. Corrección
  posible (pendiente): estratificar por clase de actividad esperada en vez de temporada.
- Cobertura de la banda del factor: ~5–8 % (celda padre-mes). Banda con error dependiente del
  tamaño, **fuera de muestra** (celda padre / región): S-NPP 82 % / 83 %; N20 81 % / 75 %;
  Terra 89 % / 75 %. Todas dentro de la meta 70–90 %.
- Verificación con la verdad del simulador (2021-07..2026-06): VIIRS convertido −0.4 % frente a lo que
  Aqua habría visto sin deriva; Aqua observado +3.0 % (efecto de la deriva simulada).

## 4. Limitaciones
- Datos sintéticos: el simulador y la armonización comparten supuestos; la validación real queda para
  la Fase R.
- Región demo = rectángulo (~165 000 km²), no un límite oficial.
- Tablas dispersas: celda-mes sin focos = 0, si el mes tiene fuente.
- Meses provisionales (NRT) y el mes en curso pueden cambiar.
