# Factibilidad: llevar la armonización de Cusco a otras regiones

*Sábado 14-nov-2026 · Gabriel · rama `gabriel2` · revisa `main` en `de50872`*

**Veredicto:** es factible, pero **por etapas**, no copiando lo de Cusco. El método sí se traslada; **los factores
`k` y `kT` de Cusco no**. En esta prueba, aplicar el `k` de Cusco falla en 12 de los 15 departamentos con muestra
suficiente. Con datos propios, solo **5 departamentos más** cumplen hoy un umbral razonable.

Evidencia en [`auditoria/factibilidad/`](auditoria/factibilidad/): scripts para repetir las pruebas y resultados.

## 1. Qué había en versiones anteriores

Las versiones anteriores eran **multirregión en estructura, pero con datos sintéticos**.

| Versión | Qué hacía | Con datos reales |
|---|---|---|
| `archivo/backend-sintetico` | 5 departamentos simulados; calibración por pares de satélites sobre celdas H3 | Nunca (su "Fase R" quedó pendiente) |
| App de Dante (FIRMS en vivo) | 6 departamentos con recuadros aproximados, sin armonizar | Sí, pero sin armonización ni límites reales |
| `main` hoy | Solo Cusco, con factores validados | Sí |

Reutilizable: la infraestructura de regiones (`build_regions.py`, límites, selección de área). **No reutilizable:**
su calibración. MAESTRO §1.6 y §12 ya dicen que los demás departamentos eran datos de prueba y que un departamento
sin factores validados se rotula "sin armonizar".

## 2. La prueba

Se descargaron los archivos públicos de FIRMS de todo Perú (MODIS 2000–2025 y VIIRS S-NPP 2012–2025; 40 archivos,
106 MB, **fuera del repositorio**) y se recalcularon `k` y `kT` **por departamento** con código independiente del
equipo (`auditoria/factibilidad/scripts/factibilidad_regiones.py`). Calibración de `k` con 2013–2019 y validación
con 2020–2024 reservado, igual que en Cusco.

**Primero se comprobó que el método coincide con el del equipo:**

| Comprobación | Equipo | Esta prueba |
|---|---|---|
| Focos filtrados de todo Perú (MAESTRO P7) | 1.295.299 | **1.295.299** |
| Focos de Cusco, MODIS / VIIRS | 15.693 / 43.086 | 15.812 / 43.267 (+0,8 % / +0,4 %) |
| `k` de Cusco | 0,330 (≥ 2.500 m) y 0,247 (< 2.500 m) | 0,276 sin estratos (queda entre ambos) |
| Error mensual de Cusco | 10–12 % | 13 % |
| Error mensual de todo Perú con un `k` único | 31–33 % | 29 % |

## 3. Resultados

- **`k` varía mucho entre departamentos:** de 0,165 a 0,348 (×2,1) entre los 16 con muestra suficiente. Amazonas,
  Loreto, Cajamarca y Piura quedan cerca de 0,2; Madre de Dios, cerca de 0,35.
- **Aplicar el `k` de Cusco falla:** en 12 de los 15 departamentos distintos de Cusco con muestra suficiente, la
  razón anual VIIRS×k / MODIS sale de 0,80–1,20 en algún año. Los peores: Amazonas (hasta 2,03), Piura (2,00),
  Cajamarca (1,97), San Martín (1,74) y Loreto (1,68).
- **Aun con `k` propio**, ningún otro departamento baja del 16 % de error mensual (Cusco: 13 %); la mediana de los
  otros 15 es 22 %.
- **`kT` es peor fuera de Cusco:** varía de 2,3 a 20 (Cusco 4,6). En la selva el error mensual llega a 77–90 %
  (San Martín 90 %, Loreto 86 %, Pasco 77 %). Allí no conviene extrapolar antes de julio de 2002.
- **Volumen:** ningún departamento supera 50.000 focos en un mes ni en un año; el mapa actual (tope de 50.000)
  serviría para cualquiera. Para todo Perú: 110.571 focos en 2024 y ~477.000 en cinco años (más que el tope de
  200.000 del CSV), así que el CSV debe ser por departamento.

### Grupos

| Grupo | Departamentos | Criterio |
|---|---|---|
| **Cumplen hoy** | Ucayali, Junín, Madre de Dios, La Libertad, Áncash | ≥ 1.000 celda-días MODIS al calibrar, error mensual ≤ 25 % y razón anual 2020–24 entre 0,80 y 1,25 con su propio `k`. Con Cusco reúnen el **41 %** de los focos del país (Cusco solo, 4,6 %). |
| **Casi** | San Martín, Huánuco, Loreto, Pasco, Puno, Amazonas, Ayacucho | Razones de hasta 1,3–1,4 o error mensual de 25–27 %. Probablemente mejoren con estratos de altitud. |
| **No viables ahora (inestables)** | Cajamarca, Piura, Lambayeque | Razón anual de 0,73 a 1,54 o más. |
| **No viables ahora (muestra)** | Apurímac, Huancavelica, Lima, Arequipa, Ica, Tumbes, Moquegua, Lima Metropolitana, Tacna, Callao | Menos de 1.000 celda-días MODIS al calibrar. Callao tiene 4 focos MODIS; Lima Metropolitana da `k` = 0,033. |

Los ocho departamentos de selva y ceja (Ucayali, San Martín, Loreto, Madre de Dios, Pasco, Huánuco, Junín,
Amazonas) concentran el 76 % de los focos del país, pero solo tres cumplen hoy.

### Tabla completa

Orden por focos VIIRS. "Razón anual" = VIIRS×k / MODIS real, mínimo–máximo de 2020 a 2024. "Error" = error mensual
mediano con 2020–24 reservado (meses con ≥ 15 celda-días MODIS). Datos en
[`por_departamento.csv`](auditoria/factibilidad/resultados/por_departamento.csv).

| Departamento | Focos MODIS / VIIRS | k propio | Razón anual 2020-24 (k propio) | Error mensual | Razón anual (k de Cusco) | kT | Error kT | Grupo |
|---|---|---|---|---|---|---|---|---|
| Ucayali | 59,900 / 162,839 | 0.301 | 0.83–1.13 | 23 % | 0.76–1.03 | 10.7 | 40 % | Cumple |
| San Martín | 55,764 / 151,692 | 0.227 | 0.95–1.44 | 22 % | 1.16–1.74 | 11.5 | 90 % | Casi |
| Huánuco | 41,450 / 110,228 | 0.284 | 0.96–1.31 | 17 % | 0.93–1.27 | 13.0 | 45 % | Casi |
| Loreto | 28,272 / 92,411 | 0.206 | 0.94–1.26 | 18 % | 1.26–1.68 | 20.1 | 86 % | Casi |
| Junín | 24,771 / 75,527 | 0.249 | 0.97–1.12 | 17 % | 1.07–1.24 | 6.7 | 37 % | Cumple |
| Madre de Dios | 28,117 / 71,640 | 0.348 | 0.99–1.12 | 16 % | 0.78–0.89 | 11.1 | 34 % | Cumple |
| **Cusco** | 15,812 / 43,267 | 0.276 | 0.84–1.05 | 13 % | 0.84–1.05 | 4.6 | 41 % | Referencia |
| Pasco | 14,699 / 37,775 | 0.274 | 1.04–1.18 | 27 % | 1.04–1.19 | 18.1 | 77 % | Casi |
| Cajamarca | 8,252 / 30,720 | 0.204 | 0.75–1.46 | 23 % | 1.01–1.97 | 2.9 | 32 % | No viable (inestable) |
| Piura | 6,594 / 25,843 | 0.213 | 1.15–1.54 | 27 % | 1.48–2.00 | 2.4 | 42 % | No viable (inestable) |
| La Libertad | 8,359 / 24,877 | 0.266 | 0.87–1.11 | 16 % | 0.90–1.15 | 2.7 | 31 % | Cumple |
| Puno | 6,304 / 20,429 | 0.257 | 0.65–1.11 | 25 % | 0.70–1.19 | 2.8 | 30 % | Casi |
| Amazonas | 5,328 / 20,346 | 0.165 | 0.82–1.21 | 25 % | 1.38–2.03 | 4.3 | 39 % | Casi |
| Ayacucho | 5,979 / 17,699 | 0.246 | 0.74–1.02 | 19 % | 0.83–1.14 | 5.3 | 34 % | Casi |
| Áncash | 4,807 / 16,362 | 0.231 | 0.81–1.11 | 20 % | 0.96–1.32 | 2.9 | 26 % | Cumple |
| Lambayeque | 5,414 / 14,056 | 0.319 | 0.73–1.50 | 27 % | 0.63–1.30 | 2.3 | 21 % | No viable (inestable) |
| Apurímac | 3,492 / 10,272 | 0.267 | 0.72–1.50 | 25 % | 0.74–1.55 | 4.1 | 37 % | No viable (muestra) |
| Huancavelica | 2,130 / 7,851 | 0.226 | 0.80–1.18 | 24 % | 0.97–1.44 | 4.8 | 42 % | No viable (muestra) |
| Lima | 2,138 / 7,625 | 0.207 | 0.81–1.10 | 33 % | 1.08–1.46 | 2.7 | 18 % | No viable (muestra) |
| Arequipa | 2,113 / 7,614 | 0.242 | 0.88–1.53 | 33 % | 1.00–1.75 | 4.3 | 56 % | No viable (muestra) |
| Ica | 916 / 4,706 | 0.119 | 0.59–1.17 | 61 % | 1.36–2.70 | 1.9 | – | No viable (muestra) |
| Tumbes | 1,056 / 3,059 | 0.313 | 1.21–2.43 | 19 % | 1.07–2.14 | 1.9 | 28 % | No viable (muestra) |
| Moquegua | 649 / 1,867 | 0.333 | 0.82–2.97 | – | 0.68–2.46 | 2.8 | – | No viable (muestra) |
| Lima Metropolitana | 24 / 760 | 0.033 | 0.81–0.81 | – | 6.89–6.89 | 3.0 | – | No viable (muestra) |
| Tacna | 143 / 749 | 0.148 | 0.50–2.62 | – | 0.93–4.87 | 2.5 | – | No viable (muestra) |
| Callao | 4 / 119 | 0.073 | – | – | – | – | – | No viable (muestra) |

## 4. Costo técnico

Medido con todo Perú cargado en las tablas DuckDB en memoria que usa hoy la app
(`auditoria/factibilidad/scripts/capacidad_peru.py`; los pesos son sintéticos, importan la forma y el tamaño):

| | Cusco hoy | Todo Perú |
|---|---|---|
| Filas: focos / celda-día | 58.779 / 36.260 | 1.295.299 / ~1,0 M (1,26 M en la prueba) |
| Parquet en disco | 3,6 MB | 70 MB (los CSV de Perú, ~225 MB, no caben en GitHub: MAESTRO P7) |
| Memoria de las tablas DuckDB | 20 MB | **~450 MB** |
| Carga al arrancar | 1,6 s | 3,6 s |
| Focos de un departamento, un año | 43 ms | 99 ms (16.713 filas) |
| Focos de todo Perú, un mes | – | 148 ms (27.870 filas) |
| CSV de todo Perú, un año | – | 0,9 s (110.571 filas; tope actual 200.000) |

- **Cloud Run:** hoy 1 GiB. Con todo Perú, las tablas (~450 MB) más el proceso (~170 MB), la caché y el armado de
  respuestas grandes, queda justo; recomiendo **2 GiB** (estimación, no probada).
- **Caché de respuestas** (`api/cache.py`): con 27 regiones habría ~35.000 respuestas posibles frente a un tope de
  3.000 (estimación); hay que subir `response_cache.max_items` y `max_mb`.
- **Acoplamiento a Cusco** (menciones en el código, incluye comentarios y mensajes): backend 64 en 10 archivos,
  interfaz 50 en 4, scripts de armonización 41 en 9, pruebas 57 en 5. Las dependencias estructurales:
  `CUSCO = 'PE-CUS'` y los textos de la interfaz, las constantes `REGION_CODE` / `COVER_*`, las sumas de control
  SHA-256 de `sources.CONTROL`, el límite de Cusco como única región válida (`_require_inside`) y los casos de
  MAESTRO §12 en las pruebas.
- **Cómputo de recalibrar:** todo Perú toma 12 s; el costo real es validar y revisar cada departamento.

## 5. Ruta recomendada

1. **Antes del congelamiento de código del domingo (21:30):** no ampliar la cobertura validada. Usar este resultado
   en la metodología como respuesta a "¿por qué solo Cusco?" y declararlo en "Qué no hace".
2. **Opcional y barato:** mostrar los demás departamentos como **"sin armonizar"** (conteos crudos por sensor, sin
   sumar), como ya permite MAESTRO §1.6. Nunca mezclados en totales ni comparaciones con Cusco.
3. **Después, por fases** (estimación de esfuerzo de una persona, no medida):
   - **(a)** Parametrizar los scripts de armonización y el backend por región, con un **manifiesto por región**
     (código, límite, factores, cobertura y sumas de control). Reemplaza las constantes y las sumas de control fijas.
   - **(b)** Añadir **altitud SRTM por teselas** (Earth Engine limita `sampleRectangle` a 262.144 píxeles por
     llamada: MAESTRO P7). En Cusco los dos estratos difieren un 34 % (0,330 frente a 0,247), así que importa.
   - **(c)** Habilitar primero los cinco que cumplen, cada uno con su `k` y su validación, y publicar el error
     mensual por región (criterio de MAESTRO P7). 2–3 días.
   - **(d)** Resolver los "casi" con estratos; dejar fuera los que no pasen. 2–3 días más.
   - **(e)** Servir con Parquet por región y año, `region` como columna, selector de región en la interfaz y 2 GiB
     en Cloud Run.

## 6. Límites de este análisis

- **Sin estratos de altitud.** No hay SRTM aquí (requiere Earth Engine). La prueba sirve para comparar
  departamentos entre sí y contra Cusco, **no para fijar los factores finales**.
- **Referencia en deriva.** MODIS pierde sensibilidad desde ~2020 (deriva orbital, según MAESTRO), así que parte de
  las razones mayores que 1 puede ser MODIS y no error de `k`. Afecta a todos los departamentos, también a Cusco.
- **Límite administrativo distinto.** Se usó geoBoundaries ADM1; el equipo usa FAO GAUL. En Cusco la diferencia es
  de ±0,8 % en los focos, pero los factores finales deberían usar un solo límite para todas las regiones.
- **Umbrales propios.** Los umbrales del grupo "Cumplen hoy" los fijé yo para ordenar la tabla; el equipo debería
  confirmarlos antes de usarlos como criterio de publicación.
- **Memoria de la prueba de capacidad.** Los departamentos de esa prueba se asignaron al azar para poder filtrar
  consultas (inflan las celdas-día a 1,26 M frente a ~1,0 M reales). Los pesos `eq_*` también son sintéticos.

## 7. Cómo repetirlo

Necesita los datos públicos de FIRMS en una carpeta aparte (no se versionan: MAESTRO §11) y los límites ADM1,
que están en la rama `archivo/backend-sintetico`:

```powershell
# 1. Límites de los departamentos (geoBoundaries ADM1, de la rama de archivo)
git show origin/archivo/backend-sintetico:plataforma_local/backend/config/regions_src/geoBoundaries-PER-ADM1_simplified.geojson > adm1.geojson

# 2. Archivos públicos de FIRMS por país (~106 MB, ~2,5 min)
mkdir firms_peru_raw
foreach ($y in 2000..2025) { curl.exe -sS -f -o "firms_peru_raw\modis_${y}_Peru.csv" "https://firms.modaps.eosdis.nasa.gov/data/country/modis/$y/modis_${y}_Peru.csv" }
foreach ($y in 2012..2025) { curl.exe -sS -f -o "firms_peru_raw\viirs-snpp_${y}_Peru.csv" "https://firms.modaps.eosdis.nasa.gov/data/country/viirs-snpp/$y/viirs-snpp_${y}_Peru.csv" }

# 3. Factores por departamento y validación (~12 s)
$py = "plataforma_local\backend\.venv\Scripts\python"
& $py -I -X utf8 -W ignore auditoria\factibilidad\scripts\factibilidad_regiones.py firms_peru_raw adm1.geojson por_departamento.csv

# 4. Costo de servir todo Perú en memoria (~2 min)
& $py -I -X utf8 -W ignore auditoria\factibilidad\scripts\capacidad_peru.py firms_peru_raw parquet_tmp
```

Resultados guardados en [`auditoria/factibilidad/resultados/`](auditoria/factibilidad/resultados/).
