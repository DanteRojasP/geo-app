# Para revisar, Antonio: días sin VIIRS S-NPP en la serie de Cusco

*Domingo 15-nov-2026 · Julio · detalle en `REVISION_FACTIBILIDAD_REGIONES.md` §2.1*

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

## Actualización (15-nov, tarde): NOAA-20 cubre los huecos y S-NPP dejó de publicar

Comprobado con la API de FIRMS, en el rectángulo de Cusco:

| Ventana de 5 días | VIIRS S-NPP | VIIRS NOAA-20 | MODIS |
|---|---|---|---|
| Desde el 28-jul-2022 | 0 filas | **348 filas** | 63 filas |
| Desde el 10-jul-2024 | 0 filas | **91 filas** | no consultado |

- **NOAA-20 tiene datos en los días sin S-NPP.** Es la opción recomendada para rellenarlos, con su propio `k`
  calibrado sobre el solapamiento S-NPP/NOAA-20 (2018–2026). MODIS con peso 1,0 sigue siendo la opción simple.
- **FIRMS lista S-NPP en tiempo casi real solo hasta el 2-nov-2026.** NOAA-20 y NOAA-21 siguen al día. No sabemos si
  el corte es temporal o definitivo. Si es definitivo, la serie desde 2013 (solo S-NPP) no podrá extenderse sin un
  factor NOAA-20 → escala MODIS. Esto también afecta a cualquier actualización con 2026 (P6).
- El archivo procesado de S-NPP llega hasta el 31-jul-2026, igual que los de NOAA-20 y NOAA-21.

Detalle en `PROTOCOLO_PREVENTIVO.md` §6.1 y §6.2.

## Earth Engine con el proyecto de Google Cloud de Julio

Tus scripts ya leen el proyecto de `EE_PROJECT` (`harmonizacion/cusco_referencia.py` y
`harmonizacion/sequia_fuego/clima_cusco_ee.py`). Puedes usar el proyecto de Julio, `sonic-mile-514718-r5`.

**Estado hoy (15-nov, comprobado):** la API de Earth Engine está disponible para el proyecto, pero todavía **no
está activada ni registrada**. Julio es propietario, así que puede hacerlo.

**Pasos:**
1. **Julio** registra el proyecto para **uso no comercial** en https://console.cloud.google.com/earth-engine
   (NASA Space Apps califica) y activa la API `earthengine.googleapis.com`.
2. **Julio** te da acceso en el proyecto con **tu propia cuenta de Google**. Los roles que pide la guía de acceso de
   Earth Engine son "Earth Engine Resource Writer" (o "Viewer") y "Service Usage Consumer"; se confirman al
   asignarlos. **No se comparten contraseñas ni archivos de credenciales.**
3. **Tú**, en tu computadora:
   ```powershell
   pip install earthengine-api          # en un entorno aparte, no en el del backend
   earthengine authenticate             # abre el navegador: entra con tu cuenta
   $env:EE_PROJECT = "sonic-mile-514718-r5"
   ```
4. El registro no comercial se **revalida una vez al año**.

### ¿Cuántos créditos gasta?

**Earth Engine: nada, si el proyecto está registrado como no comercial.** La documentación de Google dice que la
cuenta de facturación no se cobra por el uso de Earth Engine mientras el proyecto esté registrado para uso no
comercial, aunque el proyecto pague otros servicios.

Lo que sí hay es una **cuota mensual de cómputo**, medida en EECU-hora (unidades de cómputo de Earth Engine por
hora). Es por proyecto y se reinicia el día 1 de cada mes:

| Nivel no comercial | Cuota al mes | Requisito |
|---|---|---|
| Community (por defecto) | 150 EECU-hora | Ninguno |
| **Contributor** | **1.000 EECU-hora** | Tener una cuenta de facturación activa (el proyecto de Julio la tiene). Earth Engine sigue sin cobrarse |
| Partner | 100.000 EECU-hora | Solicitud aparte; la aprobación puede tardar semanas |

Si se pasa de la cuota, **no se cobra**: el proyecto entra en modo restringido y las tareas siguen funcionando, pero
más lento. Fuente: guía de niveles no comerciales de Earth Engine (vigente desde el 27-abr-2026).

**Estimación de nuestro uso (no medida):** Cusco es una región chica (~72.000 km²).
- MODIS mensual a 1 km para 2003–2025 son ~276 imágenes de ~72.000 píxeles.
- CHIRPS a 0,05° son ~2.400 píxeles por imagen.
- Lo más pesado sería SRTM o MapBiomas a 30 m: ~80 millones de píxeles por imagen.

Calculo **unas pocas EECU-hora, del orden de 1 a 10**, para todo lo planificado: tus scripts, el NDVI y el área
quemada por zona del protocolo preventivo y MapBiomas. Está muy por debajo incluso de la cuota Community. El consumo
real se ve en Cloud Monitoring (métricas de Earth Engine); conviene mirarlo después de la primera corrida.

**Lo que sí puede generar costos (aparte de Earth Engine):**
- Exportar resultados a Cloud Storage: centavos por GB al mes.
- Los servicios que ya usa la app (Cloud Run, Artifact Registry, Secret Manager), que ya se pagan con el crédito.
- Activar otras APIs de pago en el proyecto: Google recomienda no activar nada fuera de Earth Engine sin avisar.

Lo más simple para no gastar nada es descargar los resultados a tu computadora (`getInfo`, o exportar a Drive) en
vez de a Cloud Storage.

**Earthdata de NASA** es otra cuenta, aparte de Google Cloud: registro gratuito con correo en
https://urs.earthdata.nasa.gov. Para estos scripts no hace falta, porque Earth Engine ya tiene MODIS, CHIRPS, SRTM y
SMAP.

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
