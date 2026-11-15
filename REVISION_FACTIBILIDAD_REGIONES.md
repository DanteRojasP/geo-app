# Revisión de la factibilidad regional de Gabriel: las regiones mapeadas al inicio

*Domingo 15-nov-2026 · Julio · revisa `FACTIBILIDAD_REGIONES.md` (Gabriel, rama `gabriel2`, `93af263`)*

Las regiones mapeadas al inicio fueron las del **sur del Perú** del backend sintético: Cusco, **Apurímac, Ayacucho,
Puno y Madre de Dios** (`archivo/backend-sintetico`, `settings.yaml`).

## 1. ¿Se sostiene la auditoría de Gabriel?

**Sí.** Repetí su script con los mismos archivos públicos de FIRMS (40 archivos, 107 MB, fuera del repositorio) y sus
números salen idénticos:
- 1.295.299 focos filtrados en Perú;
- Cusco con +0,8 % (MODIS) y +0,4 % (VIIRS) frente al equipo;
- `k` sin estratos de 0,276;
- la misma tabla por departamento.

El método coincide con MAESTRO §3:
- filtros `type = 0`, MODIS con confianza ≥ 30 y VIIRS `n`/`h`;
- celda-día de 0,01°;
- calibración con 2013–19 y validación con 2020–24.

Sus advertencias son correctas: no hay estratos de altitud, el límite es geoBoundaries (no FAO GAUL) y los umbrales
de los grupos los fijó él.

## 2. Lo que agrego para las regiones iniciales

Scripts en `auditoria/factibilidad/scripts/`:
- `regiones_iniciales.py`;
- `regiones_iniciales_sin_huecos.py`;
- `huecos_viirs.py`.

Resultados en `auditoria/factibilidad/resultados/`. Revisé tres cosas:
1. **Intervalo de confianza:** bootstrap de la razón anual. Sirve para saber si un año "fuera de 0,80–1,20" es un sesgo
   real o falta de muestra.
2. **Un `k` regional "sur andino":** calibrado con Cusco, Puno, Ayacucho y Apurímac juntos.
3. **Los días en que VIIRS S-NPP no entregó datos.**

### 2.1 Hallazgo principal: huecos de VIIRS S-NPP (afecta también a Cusco y a la app)

VIIRS S-NPP no tiene **ninguna** detección en todo Perú en estos tramos de la temporada de fuego:
- del **27-jul al 10-ago de 2022** (15 días);
- **18 días** de junio a noviembre de 2024, por ejemplo del 10 al 15 de julio y del 24 al 28 de julio.

La serie armonizada usa solo `VIIRS*k` desde 2013. Por eso **esos días valen 0**, aunque MODIS sí detectó fuego en
ellos. En Cusco:

| Mes | La app muestra | Con MODIS en los días sin VIIRS | Diferencia |
|---|---|---|---|
| 2022-07 | 54 | ~100 | **+85 %** |
| 2024-07 | 46 | ~79 | **+72 %** |
| 2023-07, 2024-06, 2025-07 | 66 / 28 / 58 | 72 / 31 / 63 | +9 a +11 % |
| 2022-08, 2024-09 | 158 / 223 | 164 / 225 | +1 a +4 % |

Consecuencias:
- Julio de 2022 y julio de 2024 aparecen como meses "bajos" en el calendario y en la anomalía. Es un **artefacto de
  datos**, no menos fuego.
- La validación de 2022 y 2024 de **todos** los departamentos incluye esos días en cero. Por eso parte de las razones
  menores que 1 de esos años no es un error de `k`.

**Recomendación para Antonio (dueño de los datos, MAESTRO §6):** en los días sin VIIRS, usar MODIS (peso 1,0, como
en 2002–2012) o VIIRS NOAA-20 con su propio `k`, y marcar esos días con otra `calidad`. Cambia las sumas de control,
así que se hace con una nueva versión de los datos (P6). No lo modifiqué.

### 2.2 Cada región inicial

Razón anual VIIRS×k / MODIS en 2020–24, sin los días del hueco (`k` propio). Entre corchetes, lo que daba con los
días del hueco, cuando cambia.

| Región | `k` propio | Razón anual 2020–24 | Error mensual | Con `k` de Cusco | `kT` (error) | Veredicto |
|---|---|---|---|---|---|---|
| **Madre de Dios** | 0,348 | 1,00–1,12 (IC estrechos) | 16 % | 0,78–0,89: **subestima 11–22 %** | 11,1 (34 %) | **Lista para armonizar con su propio `k`.** La razón MODIS/VIIRS es estable todos los años (0,31–0,36). Antes de jul-2002, mejor "sin dato" que extrapolar. |
| **Ayacucho** | 0,246 | 0,76–1,02 (2022: 0,76; 2023: 0,82) | 17–19 % | 0,83–1,14 | 5,3 (34 %) | **Casi.** Solo 2022 queda fuera, y su intervalo toca la banda. Con el `k` sur andino: 0,82–1,10. |
| **Puno** | 0,257 | 0,69–1,13 [0,65–1,11] | 24 % | 0,70–1,19 | 2,8 (30 %) | **Casi, al límite.** 2022 (0,69) es un fallo real: IC 0,61–0,70. |
| **Apurímac** | 0,267 | 0,73–1,50 | 24–25 % | 0,74–1,55 | 4,1 (37 %) | **No todavía.** Muestra chica (747 celdas-día MODIS al calibrar); 2023 se basa en 37 celdas-día (IC 1,16–2,04). |
| Cusco (referencia) | 0,276 | 0,89–1,09 [0,84–1,05] | 12–13 % | — | 4,6 (41 %) | Sin el hueco, 2022 sube de 0,84 a 0,89. |

### 2.3 El año 2022 en los Andes

Aun sin los días del hueco, en 2022 la razón MODIS/VIIRS sube **a la vez** en los cuatro departamentos andinos. No
pasa en la selva:

| | 2013–19 (media) | 2022 |
|---|---|---|
| Puno | 0,26 | 0,375 |
| Apurímac | 0,26 | 0,367 |
| Ayacucho | 0,24 | 0,323 |
| Cusco | 0,27 | 0,308 |
| Madre de Dios | 0,35 | 0,347 |

Eso indica que el `k` andino **cambia con el año**: es una señal común de toda la región, no un error de cada
departamento. Una explicación posible es un régimen de fuego distinto: con fuegos más grandes, MODIS (1 km) detecta
relativamente más. Para comprobarla haría falta área quemada (MCD64A1).

Consecuencias:
- Calibrar un `k` por departamento **no arregla** 2022. Un **`k` regional sur andino (0,265)** da el mismo error
  mensual que el `k` propio en Cusco, Puno, Ayacucho y Apurímac (12 %, 22 %, 18 % y 25 %), así que resuelve la falta
  de muestra de Apurímac sin perder precisión.
- Para los años extremos hace falta un margen. Sería como el de los meses extrapolados (MAESTRO §3), aplicado a
  `VIIRS*k` en los Andes: ±25–30 % en los peores años.
- Gabriel atribuye las razones mayores que 1 a la deriva de MODIS. **En Puno, Ayacucho y Apurímac pasa lo
  contrario:** la razón MODIS/VIIRS de 2020–24 sube +12 a +14 % frente a 2013–19, y VIIRS×k queda por debajo de
  MODIS. En Cusco no cambia (+0 %). La deriva sí podría explicar Madre de Dios (−5 %).

## 3. Ruta recomendada para las regiones iniciales

1. **Antes de todo: corregir los días sin VIIRS en Cusco** (§2.1). Es un defecto de la app actual y de la validación
   de cualquier región.
2. **Primera expansión: Madre de Dios**, con su propio `k` (0,348), validación publicada (error mensual 16 %) y sin
   extrapolar antes de julio de 2002. Ya cumple sin estratos de altitud.
3. **Segunda: Ayacucho y Puno**, con un `k` regional sur andino y el margen de año extremo. Si se usan estratos de
   altitud (SRTM por teselas, fase (b) de Gabriel), recalibrar el `k` regional por estrato.
4. **Apurímac:** con el `k` regional, solo como "sin armonizar" hasta tener más muestra o estratos.
5. Mientras tanto, como propone Gabriel: los demás departamentos en "sin armonizar" (conteos crudos por sensor, sin
   sumar), nunca en totales ni comparados con Cusco.

Coincido con Gabriel en no ampliar la cobertura validada antes del congelamiento de código. Lo de §2.1 sí conviene
avisarlo ya, porque afecta lo que muestra la app.

## 4. Límites de esta revisión

- Igual que en la auditoría de Gabriel: no hay estratos de altitud y se usó el límite geoBoundaries.
- El bootstrap remuestrea celdas-día dentro de cada año. No captura la dependencia entre días cercanos (un mismo
  fuego que dura varios días), así que los intervalos reales son algo más anchos.
- "Con MODIS en los días sin VIIRS" es una estimación: usa MODIS con peso 1,0 sin `k`, como en 2002–2012.
- La explicación de 2022 (régimen de fuego) es una hipótesis: no se probó.
