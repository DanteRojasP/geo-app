# Para revisar, Antonio: días sin VIIRS S-NPP en la serie de Cusco

*Domingo 15-nov-2026 · Julio · detalle en `REVISION_FACTIBILIDAD_REGIONES.md` §2.1*


> **Resuelto en los datos v1.3 (15-nov):** los días sin S-NPP se rellenan con **VIIRS NOAA-20** y su propio
> factor, `k20` = 0.324 (≥ 2500 m) y 0.235 (< 2500 m), calibrado con 2018–2021 sobre los días en que los dos
> satélites tienen datos y validado con 2022–2025 (NOAA-20×k20 / S-NPP×k = 0.98–1.05 por año; error mensual mediano
> 7 %). Julio de 2022 pasa de 54 a 85 y julio de 2024, de 46 a 74. Script: `harmonizacion/relleno_n20.py`; detalle en
> MAESTRO §3 (punto 8), §5, §6, §7 y §12.

## Qué pasa

VIIRS S-NPP no tiene **ninguna** detección en todo Perú en estos tramos de la temporada de fuego:
- del **27-jul al 10-ago de 2022** (15 días);
- **18 días** de junio a noviembre de 2024, por ejemplo del 10 al 15 de julio y del 24 al 28 de julio;
- algunos días sueltos en otros años.

El satélite no entregó datos esos días; no es que no hubiera fuego.

Desde 2013 la serie armonizada usa solo `VIIRS*k` (MAESTRO §3). Por eso **esos días valen 0**: en
`harmonizado_cusco_celda_dia.csv` no hay ninguna celda-día en ellos, aunque MODIS sí detectó fuego.

## Cuánto afecta (Cusco, lo que muestra la app)

| Mes | La app muestra | Con MODIS en los días sin VIIRS | Diferencia |
|---|---|---|---|
| **2022-07** | 54 | ~100 | **+85 %** |
| **2024-07** | 46 | ~79 | **+72 %** |
| 2023-07 | 66 | ~72 | +9 % |
| 2024-06 | 28 | ~31 | +11 % |
| 2025-07 | 58 | ~63 | +9 % |
| 2022-08 | 158 | ~164 | +4 % |
| 2024-09 | 223 | ~225 | +1 % |

En total son 101 celdas-día MODIS de Cusco que hoy pesan 0.

Consecuencias:
- Julio de 2022 y julio de 2024 aparecen como meses "bajos" en el calendario, en la anomalía y en "En simple". Es un
  artefacto de datos.
- La validación 2020–24 de `k` (VIIRS×k / MODIS) incluye esos días en cero. Sin ellos, la razón de Cusco en 2022 pasa
  de 0,84 a 0,89 y la de 2024, de 1,02 a 1,09.

## Propuesta (decide tú: eres el dueño de los datos, MAESTRO §6)

1. **Detectar los días sin VIIRS:** días sin ninguna detección S-NPP en todo el archivo de Perú. Con los archivos por
   país, desde 2012 son 46 días.
2. **Rellenarlos** con una de estas opciones:
   - **MODIS con peso 1,0**, como en 2002–2012. Es la opción más simple y la serie ya acepta MODIS.
   - **VIIRS NOAA-20** (desde 2018) con su propio `k`, calibrado igual que S-NPP.
3. **Marcarlos** con su propia `calidad` y `fuente_serie` (por ejemplo, `fuente_serie = "MODIS (sin VIIRS)"`), para
   que la app pueda rotularlos.
4. **Publicarlo como una nueva versión de los datos** (P6): cambian las filas y las sumas de control de MAESTRO §6,
   `verificar_datos.py` y los casos de §12 que caigan en esos meses. Avísame y actualizo la app y sus pruebas.

## Otra cosa, para cuando se amplíe a otras regiones

En 2022, aun sin los días del hueco, la razón MODIS/VIIRS sube a la vez en Cusco, Puno, Ayacucho y Apurímac (en la
selva no). Es decir, en los Andes `k` cambia con el año. Hay un detalle en `REVISION_FACTIBILIDAD_REGIONES.md` §2.3.
No afecta a la versión actual, pero sugiere poner un margen a `VIIRS*k` en años extremos.

## Cómo repetirlo

```powershell
# Archivos públicos de FIRMS de Perú (~107 MB, fuera del repo): ver FACTIBILIDAD_REGIONES.md §7
& $py -I -X utf8 -W ignore auditoria\factibilidad\scripts\huecos_viirs.py firms_peru_raw adm1.geojson
```

Salida guardada en `auditoria/factibilidad/resultados/huecos_viirs_salida.txt`.
