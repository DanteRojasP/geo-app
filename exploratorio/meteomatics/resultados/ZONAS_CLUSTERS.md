# Meteomatics por zonas homogéneas (agrupamiento con DEM) frente al fuego de Cusco

*Domingo 15-nov-2026 · Julio · `exploratorio/meteomatics/analisis_zonas.py` · datos armonizados v1.3 ·
**exploratorio** (MAESTRO §1.9; `PROTOCOLO_PREVENTIVO.md`)*

## Respuesta corta

1. **Con zonas que cubren todo Cusco y agrupadas por relieve y clima, la relación clima–fuego del mismo mes es
   claramente más fuerte** que en el análisis anterior de 8 puntos (por ejemplo, lluvia: −0,52 frente a −0,40; déficit
   de presión de vapor: +0,54 frente a +0,14). Es más fuerte en la **puna (grupo 3)** y más débil en la **selva baja
   (grupo 1)**.
2. **Para anticipar la semana siguiente, el clima ya observado aporta muy poco**: +0,008 de mejora (BSS) sobre
   calendario + fuego reciente. Es positivo, pero está por debajo del umbral del protocolo (+0,02). Ningún grupo lo
   pasa.
3. **El clima de la propia semana sí aporta** (+0,039 en todo Cusco y +0,051 en la puna) y **pasa todos los
   criterios** del protocolo en Cusco y en el grupo 3. Pero es un techo: supone un pronóstico perfecto del tiempo.
   Falta medir cuánto queda con pronósticos reales (§6).
4. **Unidad de despliegue: por zona** (con los grupos para comunicar), no por foco (§5).

## 1. Qué cambió respecto al análisis anterior

| | Antes (`INFORME.md`, `PREVENTIVO.md`) | Ahora |
|---|---|---|
| Lugares | 8 puntos, **elegidos por tener más fuego** (sesgo que advierte el protocolo) | **99 zonas** de ~28 km que cubren todo Cusco |
| Relieve | No se usaba | **DEM SRTM** (0,01°): altitud media, rugosidad, pendiente, parte sobre 3.500 m y bajo 1.500 m |
| Agrupamiento | Ninguno (un promedio ponderado) | **k-means** sobre relieve + clima, **sin el fuego** |
| Preventivo | Correlaciones con rezago | Escalera del protocolo: frente a calendario + fuego reciente, dejando un año fuera |
| Datos de fuego | v1.2 | **v1.3** (días sin S-NPP rellenados con NOAA-20) |

Meteomatics se descargó en el centro de cada zona, diario a las 18 UTC (13:00 de Perú), de 2003 a 2025: 23 años ×
99 zonas × 10 parámetros, 23 solicitudes más 6 de reintento. Los datos no se publican (licencia); quedan en
`exploratorio/meteomatics/datos/zonas/`, ignorado por git.

## 2. Los grupos

El número de grupos se eligió con el coeficiente de silueta (k = 2 a 8): **k = 3** fue el mejor (0,46).

| Grupo | Zonas | Altitud media | Rasgo | Lluvia anual | Temp. máx. jun-oct | Parte del fuego | Focos armonizados por zona y año |
|---|---|---|---|---|---|---|---|
| **1 · Selva baja** | 22 | ~700 m | 94 % bajo 1.500 m | ~2.800 mm | ~29 °C | 31 % | 8,2 |
| **2 · Ceja de selva y valles** | 38 | ~2.500 m | Pendiente media 12,5° | ~3.000 mm | ~18 °C | 44 % | 6,8 |
| **3 · Altoandino (puna)** | 39 | ~4.150 m | 91 % sobre 3.500 m | ~1.400 mm | ~13 °C | 25 % | 3,8 |

Los grupos salen geográficamente coherentes aunque no se les dio la ubicación: el grupo 1 queda al norte (cuenca baja
del Urubamba), el grupo 2 en la franja intermedia y el grupo 3 en las provincias altas del sur (figura
`zonas_clusters.png`). Asignación de cada zona en `zonas_grupos.csv`.

## 3. Análisis actual: clima y fuego del mismo mes

Correlación de Spearman de las **anomalías** de julio a octubre (cada valor menos lo habitual de ese mes), con
intervalo de confianza del 90 % por bootstrap de años:

| Conjunto | Lluvia | Déficit de presión de vapor | Aviso de incendio forestal | Humedad del suelo |
|---|---|---|---|---|
| Grupo 1 · Selva baja | −0,32 [−0,49, −0,12] | +0,33 [+0,18, +0,48] | +0,27 [+0,10, +0,43] | −0,27 [−0,42, −0,07] |
| Grupo 2 · Ceja de selva | −0,40 [−0,54, −0,24] | +0,29 [+0,12, +0,47] | +0,39 [+0,21, +0,54] | −0,38 [−0,53, −0,21] |
| **Grupo 3 · Puna** | **−0,56** [−0,69, −0,41] | **+0,57** [+0,42, +0,69] | +0,54 [+0,36, +0,69] | −0,50 [−0,67, −0,29] |
| **Cusco (99 zonas)** | −0,52 [−0,65, −0,37] | +0,54 [+0,39, +0,68] | **+0,60** [+0,43, +0,71] | −0,57 [−0,69, −0,39] |
| *Antes: 8 puntos* | *−0,40* | *+0,14* | *+0,13* | — |

92 meses (julio a octubre de 2003-2025) en cada conjunto. Las demás variables están en `zonas_actual.csv`.

Por qué cambia: los 8 puntos estaban casi todos en selva y ceja de selva (elegidos por su fuego). Ahí la relación es
más débil. La puna, donde el clima explica más, casi no estaba representada.

En la puna, un mes más seco y con más déficit de presión de vapor que lo normal tiene claramente más fuego ese mismo
mes. Es una **descripción**, no una causa: la mayoría de las quemas son agrícolas y de pastos, y el clima seco puede
tanto favorecerlas como coincidir con las fechas en que se queman.

## 4. Análisis preventivo: la semana siguiente

Comparación con la referencia del protocolo (**M2: calendario de la zona + fuego reciente**), dejando un año fuera
(2003-2025, semanas de junio a noviembre, 61.479 zonas-semana). Variables climáticas: lluvia, déficit de presión de
vapor, índice de Fosberg y humedad del suelo, en anomalías estandarizadas con los años de ajuste, con efecto distinto
por grupo.

| Modelo | Conjunto | Mejora (BSS) [IC 90 %] | Años que mejora | Peor año | AUC | Captura del 10 % superior | Criterios del protocolo |
|---|---|---|---|---|---|---|---|
| **Clima ya observado** (semana anterior) | Cusco | +0,008 [+0,004, +0,012] | 17/23 | −0,012 | 0,826 → 0,829 | 36 → 36 % | No pasa (mejora < 0,02) |
| | Grupo 1 | +0,014 [+0,007, +0,023] | 15/23 | −0,025 | 0,882 → 0,884 | 37 → 38 % | No pasa |
| | Grupo 2 | +0,005 [+0,001, +0,008] | 17/23 | −0,014 | 0,815 → 0,817 | 32 → 32 % | No pasa |
| | Grupo 3 | +0,007 [−0,001, +0,016] | 14/23 | −0,028 | 0,774 → 0,781 | 31 → 32 % | No pasa |
| **Clima de la misma semana** (techo: pronóstico perfecto) | **Cusco** | **+0,039** [+0,027, +0,051] | 20/23 | −0,033 | 0,826 → 0,844 | 36 → 37 % | **Pasa** |
| | Grupo 1 | +0,037 [+0,020, +0,054] | 16/23 | −0,087 (2009) | 0,882 → 0,893 | 37 → 37 % | No pasa (peor año) |
| | Grupo 2 | +0,031 [+0,018, +0,043] | 15/23 | −0,050 | 0,815 → 0,829 | 32 → 33 % | No pasa (estabilidad) |
| | **Grupo 3 · Puna** | **+0,051** [+0,033, +0,069] | 20/23 | −0,022 | 0,774 → **0,807** | 31 → **36 %** | **Pasa** |

Cómo leerlo:
- **BSS**: mejora del error de la probabilidad frente a M2 (0 = igual). Criterios del protocolo (§9.2): ≥ +0,02 con el
  intervalo por encima de 0, mejora en ≥ 16 de 23 años, peor año ≥ −0,05, calibración entre 0,8 y 1,2 y no empeorar
  la lista del 10 % superior.
- Sin las semanas con días sin VIIRS el resultado no cambia (+0,008 y +0,039): con los datos v1.3 esos días ya
  están rellenados.

Conclusiones:
- **El tiempo que ya pasó no anticipa** el fuego de la semana siguiente más allá de lo que dicen el calendario y el
  fuego reciente. Coincide con `PREVENTIVO.md`.
- **El tiempo de la propia semana sí agrega información**, sobre todo en la **puna**: mejora la capacidad de ordenar
  zonas (AUC +0,033) y la lista del 10 % superior captura 5 puntos más del fuego. Para usarlo de forma preventiva hace
  falta **pronosticar** ese tiempo; el resultado de arriba es el máximo posible.

## 5. ¿Desplegar por foco o por zona?

**Por zona**, y comunicar por grupo:

| | Por zona (recomendado) | Por foco |
|---|---|---|
| Existe antes del fuego | Sí: la zona siempre existe | No: un foco solo existe después de detectarse |
| Sirve para prevención | Sí: se puede dar una probabilidad por zona y semana | No: no hay nada que anticipar |
| Escala del clima y del DEM | Coincide (~28 km, ERA5/Meteomatics, DEM agregado) | El clima a 1 km no es más preciso en montaña |
| Validable | Sí: ya está validado arriba, por zona y por grupo | Solo descriptivamente |
| Comunicación | Grupos con nombre (selva baja, ceja de selva, puna) y, más adelante, provincias | Miles de puntos |

El enfoque por foco solo tendría sentido en el modo descriptivo: mostrar en la ventana de cada foco el tiempo que
hacía ese día. Es de bajo valor y no requiere un módulo aparte.

## 6. Qué falta antes de llevarlo a la plataforma

1. **Probar con pronósticos reales** (protocolo §9.3, paso 2). Open-Meteo ofrece un archivo de pronósticos pasados y
   "corridas anteriores" sin clave (verificado el 15-nov). Si con pronósticos de 7 días la mejora en la puna sigue por
   encima de +0,02, el producto B del protocolo tiene base en el grupo 3.
2. **No depender de Meteomatics para operar:** la cuenta de prueba vence el **22-nov-2026** y su licencia no permite
   publicar los datos. Repetir el análisis con Open-Meteo/ERA5 (abiertos) y confirmar que el resultado se mantiene.
3. **Prueba prospectiva** en la temporada de junio a noviembre de 2027 (protocolo §9.5).
4. **Decisión del equipo sobre el vocabulario** (protocolo §14, D1) antes de mostrar niveles en la app.

Lo que sí se puede mostrar ya, como **descripción**: el mapa de los tres grupos y una frase por grupo del análisis
actual (por ejemplo: "En la puna, los meses más secos de lo normal tienen más fuego ese mismo mes"). Solo usa
coeficientes, no datos de Meteomatics.

## 7. Límites

- **Exploratorio:** se hicieron decenas de pruebas sobre los mismos 23 años. Los umbrales del protocolo ayudan, pero
  la confirmación real es la prueba prospectiva.
- **El techo no es un pronóstico:** usa el tiempo que realmente ocurrió.
- **Modelo de Meteomatics desconocido** detrás de cada variable histórica, y valores a las 13:00 locales, no promedios
  diarios.
- **Grupos con k-means:** dependen de qué variables se usan y de su escala. k = 3 fue el mejor por silueta, pero k = 4 y
  k = 5 quedaron cerca (0,42–0,43).
- **El intervalo por años** no captura del todo la dependencia entre zonas vecinas de un mismo año.

## Archivos

- `exploratorio/meteomatics/descargar_zonas.py`: descarga de las 99 zonas.
- `exploratorio/meteomatics/analisis_zonas.py`: análisis completo.
- Resultados:
  - `ZONAS_salida.txt`;
  - `zonas_grupos.csv` (zona → grupo);
  - `zonas_actual.csv`;
  - `zonas_preventivo.csv`;
  - `zonas_clusters.png`.
