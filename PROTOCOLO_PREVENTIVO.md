# Protocolo de evaluación preventiva con múltiples fuentes · Nikal Cusco

*Domingo 15-nov-2026 · Julio · rama `julio/actividades` · estado: **propuesta para decisión del equipo***

Este documento fija **antes de ejecutarlo** cómo se evaluaría un estado preventivo del fuego en Cusco combinando
varias fuentes de datos, y registra **qué herramientas hay y cuáles faltan** (credenciales, APIs, créditos y
programas). Sigue las reglas de `MAESTRO.md` y la disciplina de `harmonizacion/sequia_fuego/PROTOCOLO.md`.

Todo lo marcado como "verificado" se comprobó hoy desde esta máquina. Se puede repetir con
`exploratorio/preventivo/verificar_herramientas.py` (§15).

---

## 0. Resumen

**Qué se propone.** Tres productos, de más sólido a menos sólido:

| Producto | Pregunta que responde | Base | Estado |
|---|---|---|---|
| **A. Calendario de preparación** | ¿Cuándo y dónde suele haber fuego? | Nuestra serie armonizada | Se puede hacer ya. No necesita nada externo. |
| **B. Condiciones de la semana** | ¿La próxima semana pinta como lo habitual, o por encima? | Calendario + fuego reciente + tiempo + vegetación | Hay que validarlo (§9). Faltan dos credenciales gratuitas y programas (§5). |
| **C. Perspectiva de temporada** | ¿La temporada jul–oct será baja, normal o alta? | El Niño, sequía, vegetación | Por defecto **no se publica**: con 23 años no se puede demostrar que sirva (§9.4). |

**Lo que ya sabemos (medido):**
- El **calendario propio** es, de lejos, lo que más anticipa: ordena bien las zonas y semanas con fuego (AUC 0,82–0,85).
- El **fuego de la semana anterior** agrega una mejora pequeña pero consistente (en 19 de 23 años).
- El **clima de Meteomatics no anticipa** el fuego de la semana, el mes ni la temporada siguientes
  (`exploratorio/meteomatics/resultados/PREVENTIVO.md`).
- Por eso el protocolo exige que cada fuente nueva **demuestre que mejora** lo que ya dan el calendario y el fuego
  reciente. Si no lo demuestra, no entra.

**Herramientas: qué falta (detalle en §5).**

| Qué | Estado | Urgencia |
|---|---|---|
| Clave de NASA FIRMS | ✅ Funciona, en Secret Manager | — |
| Fuentes sin clave (Open-Meteo, NASA POWER, NOAA, CHIRPS, Planetary Computer) | ✅ Responden | — |
| **Meteomatics** | ⚠️ La cuenta de prueba **vence el 22-nov-2026** | Decidir antes del 21-nov |
| **Earth Engine** | ❌ Sin instalar, sin credenciales y sin activar en el proyecto | Media: hay alternativa sin clave |
| **Copernicus (índice de fuego FWI)** | ❌ Falta cuenta gratuita y su clave | Media: hay alternativa sin clave |
| **NASA Earthdata** | ❌ Falta cuenta gratuita | Baja |
| Programas de Python para grillas y mapas | ❌ Faltan 11 paquetes | Alta para la Fase 2, se instala en minutos |
| Crédito de Google Cloud | ⚠️ Facturación activa; **el saldo no se puede leer desde aquí** | Revisar en la consola |
| Registros de emergencias (INDECI, SERFOR) | ❌ No hay API: hay que pedirlos | Alta para validar contra incendios reales |

**Dos hallazgos de datos que condicionan todo:**
1. **VIIRS S-NPP dejó de publicar en tiempo casi real el 2-nov-2026** (FIRMS lo lista hasta esa fecha; NOAA-20 y
   NOAA-21 siguen al día). La serie armonizada desde 2013 depende solo de S-NPP. Un sistema preventivo tiene que
   poder seguir con NOAA-20/21 (§6.2).
2. **Los días sin S-NPP valen 0 en la serie** (`revisar_antonio.md`). Hay que corregirlo antes de entrenar o validar
   nada. Comprobado hoy: **NOAA-20 sí tiene datos en esos días** (§6.1).

**Antes del congelamiento de código de hoy (21:30): no agregar nada preventivo a la app.** Este documento es el
entregable.

---

## 1. Qué es y qué no es

**Es** una descripción, con probabilidades validadas, de si las condiciones de una zona y una semana se parecen a
las que históricamente acompañaron al fuego. Sirve para ordenar la atención: dónde mirar primero.

**No es:**
- Un pronóstico de incendios. Un foco de calor es un píxel con anomalía térmica, no un incendio (MAESTRO §1.2–1.3).
- Una alerta oficial. Las emiten SENAMHI, INDECI, SERFOR y el COER de Cusco. Este producto las complementa y debe
  enlazarlas; nunca contradecirlas en pantalla.
- Una estimación de área quemada ni de daños.
- Algo que funcione fuera de Cusco. Los factores `k` y `kT` y todo lo entrenado son de Cusco (MAESTRO §1.8).

**Vocabulario.** Las reglas del equipo vetan "riesgo", "alerta" y "evento" en la interfaz, y dicen que las
analíticas describen y no pronostican. Un estado preventivo toca ese límite, así que necesita una **decisión
explícita del equipo** (§14, D1). Propuesta de nombres:

| En vez de | Usar |
|---|---|
| Riesgo de incendio | **Condiciones para el fuego** |
| Alerta | **Nivel de atención** |
| Predicción / pronóstico | **Perspectiva** (y siempre con su acierto histórico al lado) |
| Evento | **Semana con fuego** (zona con al menos un foco armonizado en la semana) |

---

## 2. Punto de partida: lo que ya está medido

### 2.1 Línea de referencia con nuestros propios datos

Medido hoy con `exploratorio/preventivo/linea_base.py`: zonas dentro de Cusco × semanas de junio a noviembre,
2003–2025, dejando un año fuera cada vez (se ajusta con 22 años y se prueba en el otro).

| | Zonas de ~28 km | Zonas de ~11 km |
|---|---|---|
| Zonas / zonas-semana | 99 / 61.479 | 602 / 373.842 |
| Semanas con fuego | 16,9 % | 4,6 % |
| **Calendario** frente a una tasa única: mejora del error (BSS) | **+0,202** | **+0,143** |
| Calendario: capacidad de ordenar (AUC) | 0,824 | 0,853 |
| **+ fuego de la semana anterior**, frente al calendario (BSS) | **+0,049** (IC 90 %: +0,031 a +0,067) | +0,024 (+0,015 a +0,033) |
| Años en que mejora | 19 de 23 | 17 de 23 |
| Peor año | 2014 (−0,043) | 2014 (−0,017) |
| Del 10 % de zonas-semana con mayor probabilidad: cuántas tuvieron fuego | 56 % | 22–23 % |
| ...y qué parte de todas las semanas con fuego capturan | 36–37 % | 54–57 % |

Cómo leerlo:
- **BSS** (habilidad de Brier) es la mejora relativa del error de la probabilidad frente a otro método. 0 = igual;
  positivo = mejor.
- **AUC** mide si las zonas con fuego reciben más probabilidad que las que no. 0,5 = azar; 1 = perfecto.
- El calendario solo ya es fuerte. El fuego reciente mejora la probabilidad, pero **no mejora la lista del 10 %
  superior**: ordena casi igual.
- Esta es la vara: una fuente nueva tiene que mejorar la segunda fila ("calendario + fuego reciente").

Salida completa: `exploratorio/preventivo/resultados/linea_base_salida.txt`. Es exploratorio y usa la serie actual,
que todavía tiene los días sin VIIRS en cero.

### 2.2 Resultados anteriores que este protocolo respeta

| Resultado | Dónde | Consecuencia |
|---|---|---|
| El clima de Meteomatics no anticipa el fuego: tras descontar el fuego reciente, \|rho\| < 0,1 a una semana y a un mes | `PREVENTIVO.md` | El clima entra solo si mejora la línea de referencia en la validación. |
| A escala de temporada, ningún predictor acierta el tercil mejor que el azar (18–32 % frente a 33 %) | `PREVENTIVO.md` | El producto C no se publica por defecto. |
| En el mismo mes, más lluvia = menos fuego (rho = −0,40) | `INFORME.md` | El pronóstico del tiempo de la propia semana sí podría aportar. Es la hipótesis principal (§7). |
| Muestra efectiva ≈ 23 años; con 80 % de potencia solo se detecta \|rho\| ≥ 0,5 entre años | `sequia_fuego/PROTOCOLO.md` §3–4 | Los años son la unidad independiente. Nada se valida "por zonas-semana". |
| Tras una temporada alta suele venir una más baja (rho = −0,40, p = 0,08) | `PREVENTIVO.md` | Hipótesis del combustible consumido (H4). |
| En 2022 la relación MODIS/VIIRS cambió a la vez en los Andes | `REVISION_FACTIBILIDAD_REGIONES.md` §2.3 | El objetivo (la serie) tiene error propio en años extremos. |

---

## 3. Diseño

### 3.1 Unidades

| Elemento | Definición | Motivo |
|---|---|---|
| **Zona** (principal) | Celda de 0,25° (~28 km) cuyo centro cae dentro de Cusco: **99 zonas** | A 28 km hay fuego en el 17 % de las semanas: suficiente para estimar probabilidades. Coincide con la resolución de ERA5. |
| Zona fina (secundaria) | Celda de 0,10° (~11 km): 602 zonas | Solo para mapas; la validación principal es a 28 km. |
| Provincia (para comunicar) | Las 13 provincias de Cusco, sumando zonas | Así lo leen las autoridades. El límite provincial no está en el repositorio, pero hay una fuente abierta (§5.5). |
| **Semana** | Bloques de 7 días desde el 1 de enero (52 por año), como en `linea_base.py` | Fijos y comparables entre años. |
| Temporada de evaluación | Semanas 22 a 48 (junio a noviembre) | Concentra casi todo el fuego. |
| Años | 2003–2025 para ajustar y validar (sin focos extrapolados); 2026 y 2027 reservados (§9.5) | MAESTRO §1.5. |

Las zonas se definen por geografía, **no por cuánto fuego tuvieron**. Elegirlas por su fuego condiciona el
resultado (`sequia_fuego/PROTOCOLO.md` §2).

### 3.2 Qué se quiere anticipar

| Objetivo | Definición | Uso |
|---|---|---|
| **Y1 (principal)** | La zona tiene ≥ 1 foco armonizado en la semana | Probabilidad de "semana con fuego". |
| Y2 (secundario) | El total de la zona en la semana supera el percentil 90 de sus semanas con fuego (calculado solo con los años de ajuste) | Semanas de actividad alta. |
| Y3 (secundario) | Total semanal de focos armonizados de todo Cusco (en logaritmo) | Vista regional. |

### 3.3 Horizontes

| Horizonte | Se emite | Mira hacia | Producto |
|---|---|---|---|
| Histórico | Una vez al año | Todo el año | A. Calendario de preparación |
| Corto | Cada lunes (o a diario) | Los 7 días siguientes | B. Condiciones de la semana |
| Medio | Cada lunes | Días 8 a 14 | B, solo si pasa la validación a ese plazo |
| Temporada | 1 de abril, mayo y junio | Julio a octubre | C. Perspectiva de temporada |

### 3.4 Regla de oro del tiempo: nada del futuro

Cada dato se usa **solo si ya estaba publicado en la fecha de emisión**, según su retraso real (§4.7). En la
reconstrucción histórica se aplica el mismo retraso. Sin esta regla, la validación sale mejor de lo que el sistema
rendiría de verdad.

---

## 4. Componentes y fuentes

Seis componentes. Cada uno responde una pregunta distinta. La columna "Hoy" es el resultado de la verificación del
15-nov-2026.

### 4.1 Componente 1 · Historia propia (línea de referencia)

| Variable | Definición | Fuente | Hoy |
|---|---|---|---|
| Calendario de la zona | Frecuencia histórica de semanas con fuego en esa zona y semana del año (ventana de ±1 semana) | `harmonizado_cusco_celda_dia.csv` | ✅ En el repositorio |
| Recurrencia | En cuántos años distintos tuvo fuego cada celda de ~1 km | `/api/analitica/recurrencia` | ✅ Ya está en la app |
| Inicio, pico y fin de temporada | Semana en que el acumulado histórico cruza el 10 %, 50 % y 90 % | Serie propia | ✅ Se calcula con lo que hay |

### 4.2 Componente 2 · Observación reciente

| Variable | Definición | Fuente | Acceso | Hoy |
|---|---|---|---|---|
| Fuego la semana anterior en la zona | Sí/no y total | FIRMS casi en tiempo real: NOAA-20, NOAA-21, MODIS | API de área con MAP_KEY | ✅ Clave válida; cuota 5000 cada 10 min |
| Fuego en zonas vecinas y en todo Cusco | Zonas vecinas con fuego la semana anterior | Igual | Igual | ✅ |
| Detecciones cada 10–15 min | GOES (geoestacionario): menos detalle, mucha más frecuencia | FIRMS `GOES_NRT` | Igual | ✅ Responde (1 detección en Cusco en 2 días) |
| Área quemada reciente | Producto mensual | FIRMS `BA_MODIS`, `BA_VIIRS` | Igual | ⚠️ Aparecen en la lista de FIRMS (hasta 2026-08-01); la descarga por área **no se probó** |

Disponibilidad que informa FIRMS hoy:

| Fuente | Desde | Hasta |
|---|---|---|
| MODIS casi en tiempo real | 2026-09-01 | 2026-11-15 |
| VIIRS NOAA-20 casi en tiempo real | 2026-08-01 | 2026-11-15 |
| VIIRS NOAA-21 casi en tiempo real | 2024-01-17 | 2026-11-15 |
| **VIIRS S-NPP casi en tiempo real** | 2026-08-01 | **2026-11-02** |
| VIIRS S-NPP procesado | 2012-01-20 | 2026-07-31 |
| VIIRS NOAA-20 procesado | 2018-04-01 | 2026-07-31 |
| VIIRS NOAA-21 procesado | 2023-03-01 | 2026-07-31 |

### 4.3 Componente 3 · Tiempo y clima

| Variable | Definición | Fuente | Periodo | Resolución | Clave | Hoy |
|---|---|---|---|---|---|---|
| Lluvia, temperatura máxima, humedad, viento, racha, evapotranspiración | Diario y horario | **Open-Meteo histórico** (reanálisis ERA5) | Probado desde 1981 | ~25 km | No | ✅ |
| Lo mismo, pronosticado | 16 días | **Open-Meteo pronóstico** | Hoy + 16 días | ~10–25 km | No | ✅ (hasta 2026-11-30) |
| Pronósticos del pasado | Lo que se pronosticó entonces | **Open-Meteo, archivo de pronósticos** y "corridas anteriores" | Respondió para 2018 y 2022 | ~10–25 km | No | ✅ Responde; da también el pronóstico emitido 3 y 7 días antes. Falta confirmar desde qué año es homogéneo |
| Pronóstico por meses | Lluvia y temperatura, con varios miembros | **Open-Meteo estacional** | ~6 meses | ~1° | No | ✅ (hasta 2027-05-16) |
| Lluvia, temperatura, humedad, viento, humedad del suelo | Diario, de NASA | **NASA POWER** (MERRA-2) | Desde 1981 | ~50 km | No | ✅ |
| Lluvia por satélite y estaciones | Mensual y por pentadas | **CHIRPS** v2.0 y v3.0 (UCSB) | Desde 1981 | 0,05° | No | ✅ Carpetas accesibles |
| Lluvia oficial del Perú | Grilla de SENAMHI | **PISCO** (biblioteca del IRI) | Desde 1981 | 0,1° | No | ✅ La página responde; no se probó la descarga ni hasta qué año llega |
| **Índice meteorológico de fuego (FWI)** histórico | Estándar internacional (sequedad del combustible + viento) | **Copernicus EWDS** `cems-fire-historical-v1` | 1940 a 12-nov-2026 (catálogo) | 0,25° | **Sí (gratis)** | ❌ Falta cuenta. Licencia CC-BY |
| FWI por meses | Pronóstico estacional | Copernicus EWDS `cems-fire-seasonal` | Emisiones de 1981 a oct-2026 (catálogo) | ~1° | Sí | ❌ Falta cuenta. Licencia CC-BY |
| FWI calculado por nosotros | Con temperatura, humedad, viento y lluvia del mediodía | Open-Meteo + paquete `xclim` | Desde 1981 | ~25 km | No | ⚠️ Falta instalar `xclim` |
| Mapas de FWI | Solo para mirar | GWIS (Copernicus/JRC), servicio de mapas | Actual | — | No | ✅ 211 capas |
| ERA5 completo | Zarr público | Google Cloud `gcp-public-data-arco-era5` | 1959–2022 | 0,25° | No | ✅ Listado accesible; faltan `xarray` y `zarr` |
| ERA5-Land | Reanálisis de superficie, horario | Copernicus CDS `reanalysis-era5-land` | 1950 a 9-nov-2026 (catálogo) | 0,1° | Sí | ❌ Falta cuenta. Licencia CC-BY |
| El Niño / La Niña | Índice ONI mensual | NOAA CPC | Desde 1950 | — | No | ✅ Último valor: **ASO 2026 = +2,46** |
| Índices de fuego y sequía | Aviso de incendio forestal, Fosberg, índice de sequía | Meteomatics | 1900–2028 y pronóstico | ~1 km (modelo) | Sí | ⚠️ **Vence el 22-nov-2026**; el FWI canadiense no está en la cuenta |

Nota sobre el ONI: el último valor leído (+2,46, agosto–octubre de 2026) corresponde a **El Niño fuerte** (por
encima de +2,0). En el
sur andino El Niño suele asociarse a menos lluvia, pero con 23 años no podemos demostrar su efecto sobre el fuego
de Cusco (H6). Es un motivo para tener el producto B funcionando antes de junio de 2027, no un pronóstico.

### 4.4 Componente 4 · Combustible (vegetación)

| Variable | Definición | Fuente | Acceso | Hoy |
|---|---|---|---|---|
| Verdor (NDVI/EVI) | Cada 16 días, 250–500 m | MODIS MOD13 | **Planetary Computer** (`modis-13A1-061`, `modis-13Q1-061`), sin clave | ✅ Colecciones desde 2000 |
| | | | Earth Engine (`MODIS/061/MOD13A3`) | ❌ Sin credenciales |
| Área quemada | Mensual, 500 m | MODIS MCD64A1 | Planetary Computer (`modis-64A1-061`) | ✅ Búsqueda probada: 2 teselas cubren Cusco (h10v10, h11v10) |
| Uso del suelo | Anual, 10 m, 9 clases | Impact Observatory | Planetary Computer (`io-lulc-annual-v02`) | ✅ 2017–2024 |
| Uso del suelo del Perú | Anual, 30 m, muchas clases | MapBiomas Perú | Earth Engine o descarga | ⚠️ El sitio responde; la descarga no se probó |
| Altitud y pendiente | 30 m | Copernicus DEM / NASADEM | Planetary Computer | ✅ |
| Humedad del suelo por satélite | SMAP, 9 km, desde 2015 | NASA AppEEARS | Cuenta de Earthdata | ❌ Falta cuenta (solo 10 temporadas) |
| Temperatura de la superficie | Diaria, 1 km | MODIS MOD11 | Planetary Computer (`modis-11A1-061`) | ✅ |

No disponibles en Planetary Computer (comprobado): CHIRPS y el NDVI de VIIRS. GPM IMERG llega solo hasta mayo de
2021 y TerraClimate hasta diciembre de 2021.

### 4.5 Componente 5 · Factor humano

En Cusco la mayoría de las quemas son agrícolas o de pastos. Este componente explica **dónde** y **cuándo dentro
del año**; casi todo es fijo en el tiempo.

| Variable | Fuente | Acceso | Hoy |
|---|---|---|---|
| Fracción de cultivo y de pasto en la zona | Uso del suelo (§4.4) | Planetary Computer | ✅ |
| Distancia a carreteras y a centros poblados | OpenStreetMap | Extracto de Geofabrik para Perú | ✅ Disponible (258 MB). El servidor Overpass no respondió hoy (error 502 y tiempo agotado) |
| Centros poblados y población | INEI | Descarga manual | ❌ Sin API conocida |
| Calendario agrícola (siembra y preparación de terreno) | MIDAGRI | Documento | ❌ Manual |
| Áreas naturales protegidas | SERNANP | Descarga | No probado |
| Día de la semana y feriados | Calendario | — | ✅ |

### 4.6 Componente 6 · Verdad de campo (para validar, no para predecir)

| Variable | Fuente | Acceso | Hoy |
|---|---|---|---|
| Emergencias por incendio forestal (fecha, distrito, hectáreas) | INDECI (SINPAD), COER Cusco | Solicitud | ❌ El portal de datos abiertos no devolvió conjuntos por API; `sinpad.indeci.gob.pe` dio 404 |
| Reportes de incendios forestales | SERFOR | Visor GeoSERFOR | ⚠️ El visor responde; sin descarga automática comprobada |
| Avisos de condiciones favorables para incendios | SENAMHI | Web | ⚠️ La web responde; falta identificar el producto vigente. Sirve para no contradecirlos |

Sin esta verdad de campo solo se puede validar contra **focos**, no contra incendios. Para hablar de prevención con
autoridades, es lo más importante que falta.

### 4.7 Retraso real de cada fuente (para la regla del §3.4)

| Fuente | Retraso habitual | Cómo se usa en la reconstrucción |
|---|---|---|
| FIRMS casi en tiempo real | ~3 horas | Fuego observado hasta el día anterior a la emisión |
| Pronóstico del tiempo | 0 | En la validación histórica se usa el reanálisis como si fuera un pronóstico perfecto (§9.3) |
| ERA5 / Open-Meteo histórico | ~5 días | Variables "observadas" hasta 6 días antes |
| CHIRPS | ~3 semanas (definitivo) | Hasta el mes anterior |
| NDVI de 16 días | ~8–20 días | El compuesto de hace dos periodos |
| Área quemada MCD64A1 | ~2–3 meses | Solo temporadas anteriores |
| ONI | ~1 mes | El trimestre cerrado más reciente |

Estos retrasos son los habituales de cada producto; se confirman al armar los datos (Fase 2).

---

## 5. Herramientas: qué hay y qué falta

### 5.1 Credenciales y cuentas

| Servicio | Para qué | Estado hoy | Cómo se consigue | Costo | ¿Bloquea? |
|---|---|---|---|---|---|
| **NASA FIRMS (MAP_KEY)** | Fuego en tiempo casi real y archivo | ✅ Válida. En Secret Manager (`firms-map-key`). Consumo al verificar: 63 de 5000 en 10 min (incluye estas pruebas) | — | Gratis | No |
| **Meteomatics** | Índices de fuego, pronóstico | ⚠️ Cuenta de prueba de un compañero. **Vence el 22-nov-2026.** 1000 solicitudes por día; 211 usadas en total al verificar. No permite publicar sus datos | Pedir extensión por el beneficio de NASA Space Apps, o contratar | Comercial | No: el protocolo no depende de ella |
| **Earth Engine** | NDVI, CHIRPS, área quemada, MapBiomas, altitud | ❌ No instalado; sin credenciales; API no activada en el proyecto | 1) Registrar el proyecto para uso no comercial. 2) Activar `earthengine.googleapis.com`. 3) `pip install earthengine-api`. 4) `earthengine authenticate` (lo hace Julio en el navegador) | Gratis para uso no comercial, con cuota mensual | No: Planetary Computer cubre casi todo |
| **Copernicus (ECMWF)** | FWI histórico y estacional; ERA5-Land | ❌ Sin cuenta ni archivo `.cdsapirc` | Cuenta gratuita en ECMWF, aceptar la licencia de cada conjunto y copiar la clave personal | Gratis | No: el FWI se puede calcular |
| **NASA Earthdata** | SMAP, descargas directas de MODIS | ❌ Sin cuenta | Registro gratuito | Gratis | No |
| **Planetary Computer** | MODIS, uso del suelo, altitud | ✅ El catálogo responde sin clave | — | Gratis | No |
| **Google Cloud** | Servidor, tareas, almacenamiento | ✅ Sesión de `gcloud` activa. ❌ Sin credenciales de aplicación (ADC) | `gcloud auth application-default login` | — | Solo para Earth Engine y BigQuery desde scripts |
| **Azure** (beneficio de NASA) | Alternativa de cómputo | No configurado en esta máquina (sin `az`) | — | Crédito del beneficio | No hace falta |

Ninguna credencial debe ir al repositorio (MAESTRO §1.11). Las nuevas van a Secret Manager o a la carpeta de
credenciales fuera del repo.

### 5.2 APIs de Google Cloud (proyecto `sonic-mile-514718-r5`)

| API | Uso | Estado |
|---|---|---|
| Cloud Run | Servidor y tarea diaria | ✅ Activa |
| Cloud Storage | Guardar las tablas del estado preventivo | ✅ Activa |
| Secret Manager | Claves | ✅ Activa |
| BigQuery | Consultas (opcional) | ✅ Activa |
| Cloud Build | Construir imágenes | ✅ Activa, pero la cuenta de servicio no tiene permiso de lectura (se construye en local) |
| **Earth Engine** | NDVI, lluvia, área quemada | ❌ **Falta activar** |
| **Cloud Scheduler** | Lanzar la tarea diaria | ❌ **Falta activar** |

Activar una API es un cambio de configuración del proyecto: lo decide Julio.

### 5.3 Créditos y costos

| Concepto | Estado o estimación |
|---|---|
| Facturación del proyecto | ✅ Activa |
| **Crédito restante de la prueba de Google Cloud** | ⚠️ **No se puede leer con `gcloud`.** Revisar en la consola: Facturación → Créditos |
| Alerta de presupuesto | ❌ Sigue pendiente (recomendada desde `CAMBIOS_Y_RECOMENDACIONES.md`) |
| Servidor actual (1 instancia mínima) | ~US$0,6–1 por día (estimación anterior) |
| Tarea diaria del estado preventivo (2–5 min, 1 vCPU) | Menos de US$0,5 al mes (estimación) |
| Almacenamiento (menos de 1 GB de Parquet) | ~US$0,03 al mes (estimación) |
| Cloud Scheduler | Sin costo con pocas tareas (estimación) |
| Descargas históricas (una vez) | En local; sin costo de nube |
| Earth Engine, Copernicus, Earthdata, Open-Meteo, NASA POWER | Gratis para uso no comercial; con límites de uso que hay que confirmar al registrarse |

El estado preventivo agrega muy poco al gasto. El costo dominante sigue siendo la instancia siempre encendida.

**Open-Meteo:** el uso gratuito es para fines no comerciales y tiene un tope diario de llamadas. Para 99 zonas
alcanza de sobra en operación. La descarga histórica (23 años por zona) conviene repartirla en uno o dos días.
Confirmar las condiciones vigentes antes de la Fase 2.

### 5.4 Programas

Entorno actual: Python 3.12 con pandas, numpy, scipy, scikit-learn, shapely, pyproj, duckdb, httpx y matplotlib.

| Falta | Para qué | Necesario en |
|---|---|---|
| `xarray`, `netCDF4`, `zarr` | Leer grillas (ERA5, CHIRPS, FWI) | Fase 2 |
| `rasterio`, `geopandas` | Leer GeoTIFF, zonas y provincias | Fase 2 |
| `pystac-client`, `planetary-computer` | Buscar y descargar de Planetary Computer | Fase 2 |
| `statsmodels` | Regresiones con errores agrupados por año | Fase 3 |
| `xclim` | Calcular el FWI | Fase 2 (si no se usa Copernicus) |
| `earthengine-api` | Earth Engine | Opcional |
| `cdsapi` | Copernicus | Opcional |

Deben instalarse en un entorno **aparte** (`exploratorio/preventivo/.venv`), no en el del backend: la imagen de la
app no debe crecer (bajó de 1,33 GB a 917 MB al quitar dependencias).

### 5.5 Datos que no se consiguen con una API

| Dato | Estado | Acción |
|---|---|---|
| Registros de incendios de INDECI y SERFOR | ❌ | Solicitud formal (acceso a la información) o contacto con el COER Cusco |
| Límites de provincias | ⚠️ No están en el repositorio | geoBoundaries nivel 2: ✅ disponible (196 provincias del Perú, año 2020, licencia CC BY 3.0 IGO) |
| Límites de distritos | ❌ | geoBoundaries no tiene el nivel 3 del Perú (404). Pedir a INEI o IGN |
| Calendario agrícola | ❌ | Documento de MIDAGRI; se transcribe a mano |
| Avisos de SENAMHI | ⚠️ La web responde | Identificar el producto vigente y enlazarlo |

### 5.6 Qué pedirle a Julio (en orden)

1. Revisar el **crédito restante** en la consola de Google Cloud y crear la **alerta de presupuesto**.
2. Decidir sobre **Meteomatics** antes del 21-nov: pedir extensión o dejarla vencer (recomendado: dejarla vencer;
   Open-Meteo y NASA POWER cubren lo mismo con licencia abierta).
3. Crear la cuenta de **Copernicus** (5 minutos) si se quiere el FWI oficial en vez del calculado.
4. Registrar **Earth Engine** si se quiere MapBiomas o repetir `sequia_fuego/` (opcional).
5. Iniciar la **solicitud a INDECI/COER** de los registros de incendios: es lo que más tarda.

---

## 6. Preparación y control de calidad de los datos

### 6.1 Antes de todo: corregir los días sin VIIRS S-NPP

La serie vale 0 en los días sin S-NPP (`revisar_antonio.md`). Si no se corrige, el modelo aprende que "la última
semana de julio tiene menos fuego" y la validación de 2022 y 2024 queda sesgada.

Comprobado hoy con la API de FIRMS, en el rectángulo de Cusco:

| Ventana de 5 días | S-NPP | NOAA-20 | MODIS |
|---|---|---|---|
| Desde el 28-jul-2022 | 0 filas | **348 filas** | 63 filas |
| Desde el 10-jul-2024 | 0 filas | **91 filas** | no consultado |

NOAA-20 tiene datos en los huecos. La corrección es de Antonio (datos sellados con sumas de control).

### 6.2 Continuidad: S-NPP dejó de publicar en tiempo casi real

FIRMS lista S-NPP casi en tiempo real solo hasta el 2-nov-2026. No sabemos si es un corte temporal o definitivo.
En cualquier caso:
- El producto B **no puede depender de S-NPP**. Debe usar NOAA-20 y NOAA-21.
- Para que sus conteos sean comparables con la serie, hay que calibrar un factor **NOAA-20 → escala MODIS** (y otro
  para NOAA-21), igual que `k`. Hay solapamiento para hacerlo: S-NPP y NOAA-20 coinciden de 2018 a 2026.
- Mientras no exista ese factor, el fuego reciente se usa como **sí/no** (hubo o no detecciones en la zona), que no
  depende del factor.

### 6.3 Controles por fuente

| Fuente | Problema conocido | Control |
|---|---|---|
| Serie armonizada | Días sin VIIRS; `k` cambia en años extremos (2022); MODIS pierde sensibilidad (2025 dio 1,5) | Excluir o marcar esas semanas; repetir la validación con y sin 2022 |
| CHIRPS | Quiebre en 1999–2000 (+20 % de lluvia altoandina) | Usar solo desde 2000; anomalías respecto a 2003–2025 |
| ERA5 / Open-Meteo | Lluvia poco fiable en montaña; ~25 km | Comparar con CHIRPS y PISCO en las zonas con ambos; usar anomalías, no valores absolutos |
| NDVI | Nubes en la época de lluvias | Solo píxeles de buena calidad; compuestos de 16 días |
| Pronósticos | Cambian de modelo con los años | No mezclar versiones en la validación (§9.3) |
| Meteomatics | Modelo de fondo desconocido | No usar para validar |

### 6.4 Tabla de trabajo

Una fila por **zona × semana**, con: el objetivo de la semana siguiente, las variables de cada componente (con su
retraso aplicado), el año y un indicador de calidad. Se guarda en Parquet fuera del repositorio si incluye datos
con licencia restringida.

Toda variable climática o de vegetación entra como **anomalía**: diferencia con lo habitual de esa zona en esa
semana del año. Lo habitual se calcula **solo con los años de ajuste**, nunca con el año que se evalúa.

---

## 7. Hipótesis (fijadas antes de mirar los datos)

Cada una tiene sentido esperado y una sola forma de probarse. Lo que no esté aquí se etiqueta "exploratorio".

| | Hipótesis | Variable | Sentido | Familia |
|---|---|---|---|---|
| **H1 (principal)** | El tiempo **de la propia semana** mejora la probabilidad de semana con fuego | Anomalía del FWI medio de la semana objetivo | Más FWI → más fuego | Principal |
| H2 | La sequedad acumulada mejora la probabilidad | Días desde la última lluvia ≥ 1 mm; lluvia de 30 días (anomalía) | Más seco → más fuego | Secundaria |
| H3 | Más vegetación al final de las lluvias da más combustible | Anomalía de NDVI de marzo–abril de la zona | Más verde → más fuego | Secundaria |
| H4 | El fuego previo consume combustible | Área quemada (o focos) de la zona en las dos temporadas anteriores | Más quemado → menos fuego | Secundaria |
| H5 | Las quemas siguen el calendario humano | Día de la semana (a escala diaria) | Diferencia entre días | Secundaria |
| H6 | El clima previo anticipa la temporada | ONI de mayo–julio; lluvia de noviembre–marzo | El Niño / seco → más fuego | Aparte (temporada) |

- **Una sola prueba principal** (H1). Las secundarias (H2–H5) se corrigen con Holm.
- H6 va aparte y con la advertencia del §9.4.
- Los resultados nulos se publican igual que los positivos.
- H1 usa el tiempo de la semana que se quiere anticipar. Por eso depende de la calidad del pronóstico (§9.3).

Las variables fijas del factor humano (cultivo, caminos) **no se prueban como mejora** en Cusco: el calendario de
cada zona ya las contiene. Se usan para explicar y para cuando se amplíe a regiones sin historia.

---

## 8. Modelos: una escalera, de simple a complejo

| Modelo | Contiene | Estado |
|---|---|---|
| M0 | Una tasa única | Medido (§2.1) |
| M1 | Calendario de la zona | Medido |
| **M2** | Calendario + fuego reciente (zona, vecinas, Cusco) | Medido. **Es la referencia a superar** |
| M3 | M2 + tiempo (H1, luego H2) | Por hacer |
| M4 | M3 + vegetación (H3) | Por hacer |
| M5 | M4 + fuego de temporadas anteriores (H4) | Por hacer |
| M6 (sensibilidad) | Las mismas variables con un modelo de árboles | Solo para comprobar que no se pierde algo importante |

Reglas:
- Modelo principal: **regresión logística**, con pocos parámetros. Con 23 años independientes, cada escalón agrega
  como máximo 2 variables.
- Un escalón se acepta solo si pasa los criterios del §9.2. Si no, se descarta y se sigue con el anterior.
- No se cambia de modelo, variable ni ventana después de ver el resultado (`sequia_fuego/PROTOCOLO.md` §6).
- M6 nunca reemplaza al modelo principal salvo que pase los mismos criterios **y** esté bien calibrado.

---

## 9. Validación y criterios de aceptación

### 9.1 Esquema

- **Dejar un año fuera:** se ajusta con 22 años y se evalúa en el restante; se repite para los 23.
- **Los años son la unidad independiente.** Los intervalos de confianza se calculan remuestreando años, no
  zonas-semana.
- Todo lo que se estima (lo habitual, percentiles, coeficientes) usa solo los años de ajuste.

### 9.2 Criterios para aceptar un escalón (todos a la vez, a 28 km, objetivo Y1)

| Criterio | Umbral | Por qué |
|---|---|---|
| Mejora del error frente a M2 (BSS) | ≥ **+0,02**, con el límite inferior del IC 90 % **mayor que 0** | El fuego reciente aportó +0,049; menos de +0,02 no cambia el nivel que ve el usuario |
| Estabilidad | Mejora en ≥ 16 de 23 años | Que no dependa de 2 o 3 años |
| Peor año | No peor que −0,05 | Que no falle fuerte en un año raro |
| Calibración | Pendiente entre 0,8 y 1,2 | Si dice 30 %, que ocurra cerca del 30 % |
| Lista de atención | El 10 % superior captura al menos lo mismo que M2 | Es el uso práctico |
| Sin 2022 | Sigue mejorando al quitar 2022 | 2022 tiene un problema de medición propio |

Estos umbrales los propongo yo; el equipo debe confirmarlos **antes** de correr la Fase 3 (§14, D3).

### 9.3 El problema del pronóstico

En la reconstrucción histórica no hay pronósticos antiguos homogéneos. Se procede en dos pasos:
1. **Techo:** usar el tiempo que realmente ocurrió (reanálisis) como si fuera un pronóstico perfecto. Si ni así H1
   pasa, se descarta.
2. **Realista:** si pasa, repetir con pronósticos archivados y medir cuánto se pierde a 7 y a 14 días. El archivo
   de pronósticos de Open-Meteo **respondió hoy para 2018 y 2022**, y su servicio de "corridas anteriores" entrega
   lo que se pronosticó 3 y 7 días antes. Falta confirmar desde qué año el archivo usa un mismo modelo.

Solo el paso 2 autoriza a publicar algo que mire al futuro.

### 9.4 La temporada (producto C)

Con 23 años, solo se detectaría una relación fuerte (|rho| ≥ 0,5). Por eso:
- H6 se informa como **estimación con su intervalo**, no como prueba.
- El producto C se publica solo si se confirma en **al menos otra región** con su propia serie armonizada (por
  ejemplo, Madre de Dios) o en años nuevos.
- Mientras tanto, la app puede mostrar el estado de El Niño como **contexto**, sin traducirlo a fuego.

### 9.5 Prueba verdadera: temporada 2027

Lo anterior son reconstrucciones. La prueba que vale es prospectiva:
- Congelar el modelo y los umbrales **antes del 1 de junio de 2027**.
- Emitir cada lunes y guardar cada emisión con fecha.
- En diciembre de 2027, comparar con lo observado usando los mismos criterios del §9.2.

### 9.6 Validación contra incendios reales

Cuando lleguen los registros de INDECI o SERFOR (§4.6): medir en qué parte de los incendios reportados la zona
estaba en un nivel de atención alto la semana anterior. Sin esos registros, el producto solo puede afirmar que
anticipa **focos**.

---

## 10. Niveles y comunicación

### 10.1 Niveles (propuesta)

Por zona y semana, comparando la probabilidad del modelo con lo habitual de esa zona en esa semana:

| Nivel | Regla | Texto |
|---|---|---|
| **Habitual** | Entre 0,75 y 1,5 veces lo habitual | "Condiciones parecidas a las de esta época." |
| **Por debajo de lo habitual** | Menos de 0,75 veces | "Condiciones menos favorables al fuego que lo normal en esta época." |
| **Por encima de lo habitual** | Entre 1,5 y 2,5 veces | "Condiciones más favorables al fuego que lo normal en esta época." |
| **Muy por encima** | Más de 2,5 veces | "Condiciones mucho más favorables al fuego que lo normal en esta época." |
| **Sin base suficiente** | Zona con menos de 5 semanas con fuego en la historia, o fuente caída | "No hay historia suficiente para esta zona." |

Los cortes (0,75, 1,5 y 2,5) son provisionales. Se fijan en la Fase 3 con los años de ajuste, de modo que "muy por
encima" sea poco frecuente (alrededor del 5 % de las zonas-semana).

### 10.2 Qué acompaña siempre al nivel

- El **motivo**, en una frase: "llovió menos de lo normal en los últimos 30 días" o "hubo focos en zonas vecinas la
  semana pasada".
- El **acierto histórico** del nivel: "en el pasado, de cada 10 semanas en este nivel, N tuvieron fuego".
- La fecha de emisión y de cada fuente.
- La frase fija: "Describe condiciones, no predice incendios. Un foco de calor no es un incendio confirmado. Los
  avisos oficiales son de SENAMHI, INDECI y SERFOR."
- En inglés y en español, como el resto de la app.

### 10.3 Qué no se muestra

- Probabilidades con decimales que aparenten precisión.
- Niveles en zonas "sin base suficiente" (nunca "bajo" por falta de datos: MAESTRO §1.6).
- El producto C, salvo que pase el §9.4.
- Datos de Meteomatics (licencia).

---

## 11. Operación (si el producto B se aprueba)

| Pieza | Propuesta |
|---|---|
| Cálculo | Una tarea diaria (Cloud Run Job), lanzada por Cloud Scheduler a las 06:00 de Perú |
| Entradas | FIRMS (clave en Secret Manager), Open-Meteo, NDVI más reciente, tablas fijas del calendario |
| Salida | Un Parquet pequeño por fecha de emisión en Cloud Storage, y el último en memoria del servidor |
| Servir | `GET /api/condiciones?fecha=...`, con caché de 1 hora, como el resto de la API |
| Interfaz | Un tercer modo junto a "Serie histórica" y "En vivo", para no mezclar vistas |
| Si falla una fuente | Se mantiene la emisión anterior con aviso de "desactualizado" (como la capa En vivo). Tras 3 días, las zonas pasan a "sin base suficiente" |
| Registro | Cada emisión se guarda para la prueba del §9.5 |
| Seguimiento | Una vez al mes: comparar niveles emitidos con lo observado y publicar el resultado |

La app actual no cambia hasta entonces. La imagen del servidor no incorpora los paquetes pesados: la tarea diaria
tiene su propia imagen.

---

## 12. Fases

| Fase | Qué | Requisitos | Duración estimada |
|---|---|---|---|
| **0** | Este protocolo. Nada nuevo en la app | — | Hoy |
| **1** | Decisiones del equipo (§14). Crédito y alerta de presupuesto. Cuentas de Copernicus y Earthdata. Solicitud a INDECI | Julio | 1–3 días (la respuesta de INDECI puede tardar semanas) |
| **1b** | Corrección de los días sin VIIRS en la serie | Antonio | 1–2 días |
| **2** | Entorno aparte con los paquetes. Descarga histórica: tiempo (Open-Meteo), FWI, NDVI, área quemada, uso del suelo. Tabla de trabajo | Fases 1 y 1b | 4–6 días |
| **2b** | **Calendario de preparación** (producto A) en la app | Solo 1b | 1–2 días |
| **3** | Validación de M3 a M5 con los criterios del §9.2. Informe con resultados positivos y nulos | Fase 2; umbrales confirmados | 4–6 días |
| **4** | Si algo pasa: tarea diaria, endpoint y modo en la interfaz. Factor NOAA-20 → MODIS | Fase 3 aprobada | 5–7 días |
| **5** | Prueba prospectiva: temporada de junio a noviembre de 2027 | Modelo congelado antes del 1-jun-2027 | 6 meses |
| **6** | Otras regiones (primero Madre de Dios), cada una con su serie validada | `REVISION_FACTIBILIDAD_REGIONES.md` | Después |

Las duraciones son estimaciones para una persona; no están medidas.

El producto A no depende de ninguna herramienta que falte. Es lo primero que conviene entregar después del
congelamiento.

---

## 13. Límites y lo que puede salir mal

- **Puede que ninguna fuente externa pase.** Es un resultado posible y válido: el fuego en Cusco es sobre todo
  humano. En ese caso el producto B queda como "calendario + fuego reciente", que ya tiene acierto medido.
- **23 años son pocos.** Efectos pequeños pero reales pueden no detectarse, y algo puede pasar por casualidad. Por
  eso hay una sola prueba principal y una prueba prospectiva.
- **El objetivo tiene error.** La serie armonizada tiene ±10–13 % de error mensual en Cusco y más en años como 2022.
- **Focos no son incendios.** Sin registros de campo, no se puede afirmar nada sobre incendios.
- **Resolución.** El tiempo a ~25 km no ve valles ni laderas. En los Andes eso importa.
- **Cambios de satélite.** Si S-NPP no vuelve, la serie y el producto dependen de un factor nuevo para NOAA-20.
- **Uso indebido.** Un nivel "por debajo de lo habitual" no significa que se pueda quemar. El texto debe decirlo.
- **Autoridad.** Publicar niveles puede leerse como aviso oficial. Conviene coordinar con SENAMHI/SERFOR o, al
  menos, enlazar sus productos.
- **Licencias.** Meteomatics no permite publicar sus datos. Open-Meteo, Copernicus y NASA piden atribución.

---

## 14. Decisiones que necesita el equipo

| | Decisión | Propuesta |
|---|---|---|
| **D1** | ¿Se permite un producto que mire al futuro? Hoy las reglas dicen que la app describe y no pronostica, y vetan "riesgo" y "alerta" | Sí, solo como "condiciones", con los nombres del §1 y con su acierto histórico visible |
| **D2** | ¿Qué productos se persiguen? | A ahora; B si pasa la validación; C no por ahora |
| **D3** | ¿Se aceptan los umbrales del §9.2? | Confirmarlos antes de la Fase 3 |
| **D4** | ¿Zona de 28 km como unidad principal? | Sí; 11 km solo para el mapa |
| **D5** | ¿Meteomatics: extensión o dejarla vencer el 22-nov? | Dejarla vencer |
| **D6** | ¿FWI oficial (cuenta de Copernicus) o calculado? | Calculado para empezar; oficial para comparar |
| **D7** | ¿Quién pide los registros a INDECI/COER? | Definir responsable esta semana |
| **D8** | ¿Antonio corrige los días sin VIIRS con NOAA-20 o con MODIS? | NOAA-20, porque además resuelve la continuidad (§6.2) |

---

## 15. Cómo repetir las verificaciones

```powershell
$py = "plataforma_local\backend\.venv\Scripts\python"

# Herramientas: paquetes, credenciales, claves, APIs de Google Cloud y fuentes (no imprime claves)
& $py -I -X utf8 exploratorio\preventivo\verificar_herramientas.py "C:\ruta\a\la\carpeta\de\credenciales"

# Línea de referencia: calendario y fuego reciente (unos 30 s)
& $py -I -X utf8 exploratorio\preventivo\linea_base.py
```

Resultados de hoy en `exploratorio/preventivo/resultados/`:
- `verificar_herramientas_salida.txt`
- `linea_base_salida.txt`

Comprobaciones hechas a mano hoy y no incluidas en el script:
- Meteomatics: pronóstico a 5 días e índices de fuego disponibles; el FWI canadiense (`fwi:idx`) no está en la cuenta.
- FIRMS: NOAA-20 en los días sin S-NPP (§6.1) y GOES en Cusco.
- Planetary Computer: búsqueda de MCD64A1 sobre Cusco (2 teselas en agosto de 2024).
- Portales del Perú: `datosabiertos.gob.pe` no devolvió conjuntos por API; `geo.serfor.gob.pe` y `sinia.minam.gob.pe`
  responden; `geoidep.gob.pe` no respondió.
- Copernicus: fechas y licencia de los tres conjuntos, leídas del catálogo público.
- Open-Meteo: archivo de pronósticos (2018 y 2022) y corridas anteriores.
- geoBoundaries nivel 2 y 3 del Perú, y el extracto de OpenStreetMap de Geofabrik.

---

## Anexo A · Variables candidatas por componente

| Componente | Variable | Ventana | Entra como |
|---|---|---|---|
| Historia | Frecuencia de la zona en esa semana del año | ±1 semana, años de ajuste | Probabilidad (logit) |
| Reciente | Fuego en la zona la semana anterior | 7 días | Sí/no y logaritmo del total |
| Reciente | Zonas vecinas con fuego | 7 días, 8 vecinas | Conteo |
| Reciente | Parte de las zonas de Cusco con fuego | 7 días | Fracción |
| Tiempo | FWI medio | Semana objetivo | Anomalía |
| Tiempo | Días desde la última lluvia ≥ 1 mm | Hasta la emisión | Anomalía |
| Tiempo | Lluvia acumulada | 30 y 90 días | Anomalía (%) |
| Tiempo | Déficit de presión de vapor máximo | Semana objetivo | Anomalía |
| Tiempo | Racha máxima | Semana objetivo | Anomalía |
| Vegetación | NDVI de marzo–abril | Una vez por temporada | Anomalía |
| Vegetación | NDVI más reciente | Compuesto de 16 días | Anomalía |
| Historia de fuego | Focos armonizados de la zona en las 2 temporadas anteriores | jul–oct | Logaritmo |
| Historia de fuego | Área quemada MCD64A1 en las 2 temporadas anteriores | jul–oct | Fracción de la zona |
| Clima grande | ONI | Trimestre cerrado más reciente | Valor |
| Humano (fijo) | Fracción de cultivo y de pasto | Año más reciente | Solo para explicar |
| Humano (fijo) | Distancia media a carreteras y poblados | — | Solo para explicar |

## Anexo B · Glosario

| Término | Significado |
|---|---|
| **Foco armonizado** | Celda de ~1 km con fuego en un día, en escala equivalente a MODIS. Unidad de la app |
| **Zona** | Celda de 0,25° (~28 km) dentro de Cusco |
| **Semana con fuego** | Zona con al menos un foco armonizado en la semana |
| **Calendario** | Frecuencia histórica de semanas con fuego de una zona en una semana del año |
| **BSS** | Mejora relativa del error de una probabilidad frente a otro método (0 = igual) |
| **AUC** | Capacidad de dar más probabilidad a los casos que sí ocurren (0,5 = azar) |
| **FWI** | Índice meteorológico de fuego canadiense: combina sequedad del combustible y viento |
| **ONI** | Índice de El Niño de NOAA: anomalía de temperatura del Pacífico central |
| **Reanálisis** | Reconstrucción del tiempo pasado con un modelo y observaciones (ERA5, MERRA-2) |
| **Anomalía** | Diferencia con lo habitual de ese lugar en esa época |
| **Dejar un año fuera** | Ajustar con todos los años menos uno y evaluar en ese |
