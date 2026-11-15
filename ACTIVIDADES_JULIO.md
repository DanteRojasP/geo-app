# Actividades de Julio — Backend

NASA Space Apps Challenge 2026 · Calendario de incendios armonizado (MODIS + VIIRS)
Fuente: [PLAN.md](PLAN.md)

## Rol

**Backend.** Construir la API en FastAPI que sirve los datos armonizados (Parquet + DuckDB) al frontend.

## Entregables

- API FastAPI con los 4 endpoints mínimos.
- Carga y consulta de Parquet particionado por año y mes (DuckDB o pandas).
- Exportación de hotspots en CSV.
- Documentación OpenAPI (Swagger) de la API.

## Endpoints (contrato con Dante)

Los 4 endpoints del PLAN (`/api/calendario`, `/api/anomalias`, `/api/hotspots.csv`, `/api/metadatos`) están
implementados, más `/api/departamentos.geojson` y `/api/focos.geojson`. El contrato vigente está en
**[Protocolo de llamadas a la API](#protocolo-de-llamadas-a-la-api-contrato-con-la-interfaz)**, más abajo.

> Los formatos del plan original ("eventos", FRP, `confianza_norm`) quedaron reemplazados por el contrato de datos
> de Antonio (MAESTRO.md): la unidad es **focos armonizados** y no se usa FRP.

## Dependencias

- **Depende de:** Antonio (esquema congelado el sáb 14 a las 11:00).
- **Dependen de mí:** Dante (frontend consume el contrato de la API); Erik y Gabriel (QA sobre la API integrada).

## Cronograma

| Bloque | Actividad | Hito |
|---|---|---|
| Sáb 14 · 9:00–11:00 | Kickoff; acordar esquema y contrato de la API | Esquema congelado (11:00) |
| Sáb 14 · 11:00–17:00 | Armar la API con datos de muestra | |
| Sáb 14 · 17:00–20:00 | `/api/calendario` funcionando con datos reales | **H1 (20:00)** |
| Dom 15 · 9:00–13:00 | Integración con el frontend; `/api/anomalias` y descarga CSV | **H2 (13:00)** |
| Dom 15 · 13:00–17:00 | Corregir errores reportados en QA (mensajes claros: AOI vacío, rango invertido, sin datos, área demasiado grande) | **H3 (17:00)** |
| Dom 15 · 17:00–21:30 | Pulido, documentación OpenAPI y README | |
| Dom 15 · 21:30–23:59 | Code freeze y entrega | **H4 (21:30)** · entrega (23:59) |

## Avance (sáb 14 nov 2026)

Plataforma local funcionando en **modo sintético** en [`plataforma_local/`](plataforma_local/README.md).
Parte del backend de pruebas anterior ([project_nasa](https://github.com/Jyron1310/project_nasa), rama `backend`)
y agrega lo que pide el [PLAN.md](PLAN.md).

### Hecho

- [x] **AOI por departamento:** Cusco, Apurímac, Ayacucho, Puno y Madre de Dios (límites de geoBoundaries,
      CC BY 4.0). Se cambian con `scripts/build_regions.py`.
- [x] **Armonización A + C** (`backend/firecal/plan/`):
  - A: grilla común de 1 km; misma celda y mismo día = un evento (se conserva el de mayor FRP).
  - C: anomalía normalizada `(n − mediana) / IQR` del mismo mes dentro de su era de sensores (MODIS hasta
    ene-2012; MODIS + VIIRS desde feb-2012).
  - B (calibración por solapamiento) quedó en la rama `archivo/backend-sintetico` (retirada el 14-nov).
- [x] **Parquet particionado por año y mes**, consultado con DuckDB.
- [x] **Los 4 endpoints** (`/api/calendario`, `/api/anomalias`, `/api/hotspots.csv`, `/api/metadatos`) +
      `/api/departamentos`. Documentación OpenAPI en `/docs`.
- [x] **Errores claros** (para Erik): AOI vacío, rango invertido, sin datos, área demasiado grande, CSV demasiado largo.
- [x] **Frontend Leaflet** (base para Dante): selector de departamento o rectángulo dibujado, calendario mes × año
      (anomalía o conteo), detalle por mes, descarga CSV, metodología y créditos de FIRMS.
- [x] **Latencia medida** en cada respuesta (`X-Process-Time-ms`): 1.ª consulta de un AOI 160-540 ms; repetida ~7 ms.
- [x] **Protocolo de solicitudes:** límite por IP (429), máximo 2 consultas pesadas a la vez con semáforo (503),
      un candado por AOI y tope de 200 000 filas por CSV. Estado en `/health/limits`.
- [x] **Docker:** imagen probada (`docker compose up --build`, ~3 min; 1,57 GB; ~240 MB de RAM).
- [x] **Pruebas:** 129 (pytest) en verde, incluidas las de lógica para Gabriel (dedup, mediana, anomalía contra
      cálculo manual, conteos del calendario = filas del CSV).

### Decisión de método para revisar con Antonio

Sumar los 3 satélites VIIRS inflaba los conteos (entra NOAA-20 en 2018 y NOAA-21 en 2024) y la anomalía salía
positiva casi todos los años. Ahora se usa **un solo VIIRS a la vez** (S-NPP, luego NOAA-20) más MODIS Terra + Aqua,
y la serie empieza en 2003-01. Con eso la anomalía anual sigue el nivel de fuego simulado (Spearman 0,86) y no
salta en 2012, 2018 ni 2024.

### Cómo probarlo

```powershell
cd plataforma_local
docker compose up --build      # luego abrir http://localhost:8000
```
Sin Docker: ver [`plataforma_local/README.md`](plataforma_local/README.md), sección 3.

### Documentos

- [`plataforma_local/README.md`](plataforma_local/README.md): guía de instalación, uso y endpoints.
- [`plataforma_local/docs/DESPLIEGUE_Y_FALENCIAS.md`](plataforma_local/docs/DESPLIEGUE_Y_FALENCIAS.md): falencias
  para publicar en internet (2 y 3 ya resueltas) y procedimiento para Azure o Cloud Run.
- [`plataforma_local/docs/BENEFICIOS_NASA.md`](plataforma_local/docs/BENEFICIOS_NASA.md): qué beneficios de Space Apps
  sirven (Azure o Google Cloud + dominio de GoDaddy para publicar; Planetary Computer para validar).

## Integración con Antonio (sáb 14 nov 2026, tarde)

La plataforma ya **no usa datos sintéticos**: sirve los **datos reales de NASA FIRMS para Cusco** armonizados por
Antonio ([MAESTRO.md](MAESTRO.md), `data/harmonized/`).

### Hecho

- [x] **Merge de `antonio/modelo` en esta rama** (sin conflictos). La rama de Antonio no se tocó.
- [x] **`harmonizacion/verificar_datos.py` corre en Windows**: se caía con `UnicodeEncodeError` (`Δ` en la consola
      cp1252, y `python -I` ignora `PYTHONUTF8`). Ahora fuerza la salida a UTF-8; da `TODO OK` con el comando de
      MAESTRO §6. Registrado en MAESTRO §7 y §11.
- [x] **Backend con los CSV de Antonio** (`plataforma_local/backend/firecal/plan/`): valida columnas, filas, sumas
      y SHA-256 contra MAESTRO §6 en cada carga (~2 s) y escribe Parquet por año y mes.
- [x] **Decisiones del equipo aplicadas:**
  - Solo **Cusco**. Otra región, un área fuera de Cusco o fechas fuera de 2000-11-04 a 2025-12-31 dan
    **"sin datos"** (nunca 0). Es una serie histórica: no incluye 2026.
  - Unidad **"focos armonizados"** (Σ `eq_hotspots` / Σ `eq_foco`). Ya no se usa "evento": los datos son focos.
  - **Sin FRP** en la API ni en la web. El CSV de descarga mantiene las 18 columnas del contrato de Antonio.
  - El backend sintético anterior (`/api/v1`, 5 departamentos) quedó apagado y luego se retiró (rama `archivo/backend-sintetico`).
- [x] **Frontend según MAESTRO P2/P3:** rampa YlOrRd con cortes por cuantiles, cero gris, "sin dato" rayado,
      2000-2002 extrapolado atenuado, nota de 2025, detalle diario por mes y total igual a la descarga.
- [x] **Casos de prueba de MAESTRO §12 en pytest, todos en verde:** total 15 732 (36 260 celdas-día, 58 779 focos),
      2005 = 1355, 2012 = 678, 2013 = 424, 2020 = 1206, 2025 = 385, "sin datos" fuera de cobertura y
      Σ `eq_foco` de la descarga = total en pantalla. En total 136 pruebas pasan.
- [x] **Docker:** `docker compose up --build` en `plataforma_local/` toma los datos de la raíz del repo y los
      valida al construir (1,32 GB; ~170 MB de RAM).
- [x] **Desplegado en la plataforma local** (`C:\Nubel\local base\local_plat`, http://localhost:8000).

### Pendientes nuevos

- [ ] Analíticas descargables (MAESTRO P4): serie anual por fuente, perfil estacional, bandas de altitud.
- [ ] `harmonizacion/sequia_fuego/n_efectivo_potencia.py` tiene el mismo problema de Windows (`≈`); no se tocó.
- [ ] Desplegar en Google Cloud (proyecto listo: `sonic-mile-514718-r5`), cuando el equipo lo decida.

## Revisión de las ramas de Antonio y Dante (sáb 14 nov 2026, noche)

Detalle en [`plataforma_local/README.md`](plataforma_local/README.md), sección 8.

- [x] Integrado de `antonio/backend-modelo`: calidad del mes desde los datos (julio 2002 = referencia),
      `FIRECAL_CORS_ORIGINS` y `GET /api/departamentos.geojson`. 139 pruebas en verde.
- [x] `main` unido a esta rama (solo traía el PR #4, ya incluido).
- [ ] **Por analizar con Antonio:** margen de los meses extrapolados (`rango`, categoría `incierta`), nombres de
      campos para Dante (`eq_hotspots` frente a `focos_armonizados`) y `Dockerfile.modelo` para la nube.
- [ ] **Por analizar con Dante:** su app (React + MapLibre, FIRMS NRT de 5 días, 6 departamentos, FRP) es otro
      producto respecto al PLAN (Leaflet, calendario histórico de Cusco). Definir si se adapta al contrato de
      `/api/*` o si queda como una vista aparte de "actividad reciente".

## Interfaz de Dante y decisiones del equipo (sáb 14 nov 2026, noche)

Decisiones: MapLibre se queda, solo Cusco, los datos de Dante eran de prueba, se usa el margen de Antonio, el campo
se llama `focos_armonizados`, sin FRP y Dockerfile según el de Antonio.

- [x] **Interfaz de Dante adaptada** (`plataforma_local/frontend`, React + Vite + MapLibre):
  - **Se mantuvo:** su diseño, paneles, capas, selección de área con vista satelital y barra temporal.
  - **Se conectó** a `/api/*`.
  - **Se quitó:** los datos demo, la función FIRMS en vivo de Vercel, los otros departamentos, el FRP y el
    "riesgo" calculado con FRP.
  - **Se agregó:** el calendario mes × año del PLAN.
- [x] **Margen de los meses extrapolados** (método de Antonio): `incertidumbre`, `rango`, `anomalia_rango` y
      categoría `incierta`. Reproduce exactamente su ejemplo de agosto de 2001 (176,02; rango 98,6–253,4).
- [x] **API con `focos_armonizados`** (`total_focos_armonizados`, `matriz_focos_armonizados`, `unidad` con nombre y
      definición) y nuevo `GET /api/focos.geojson` para el mapa (peso `eq_foco`, sin FRP).
- [x] **Dockerfile basado en el de Antonio:** contexto en la raíz del repo, etapa Node para la interfaz y
      validación MAESTRO §6. Probado desde el repo y desde la copia local (1,33 GB entonces; 917 MB desde el 14-nov; ~130 MB de RAM).
- [x] 142 pruebas del backend en verde (83 desde que se retiró el backend sintético) y ESLint sin errores en la interfaz.
- [x] Desplegado en la plataforma local (http://localhost:8000).
- [ ] Siguiente: desplegar en Cloud Run (`docs/DESPLIEGUE_Y_FALENCIAS.md`, opción B) cuando el equipo lo decida.

## Protocolo de llamadas a la API (contrato con la interfaz)

**Base:** la misma dirección que sirve la página (`http://localhost:8000` en local; la URL de Cloud Run al
publicar). Si la interfaz se publica en otro dominio (p. ej. Vercel), se compila con
`VITE_API_BASE_URL=https://<api>` y en la API se define `FIRECAL_CORS_ORIGINS=https://<dominio-de-la-interfaz>`.
Todas las llamadas son **GET** y no llevan credenciales: los datos son públicos e históricos.

### 1. Qué llama la interfaz y cuándo

| Momento | Llamada | Para qué |
| --- | --- | --- |
| Al abrir | `GET /api/departamentos.geojson` | Contorno de Cusco para el mapa |
| Al abrir | `GET /api/metadatos` | Unidad, método, créditos |
| Al abrir | `GET /api/calendario?departamento=PE-CUS` | Calendario completo 2000-11 a 2025-12 |
| Al elegir año o mes | `GET /api/focos.geojson?departamento=PE-CUS&fecha_inicio=AAAA-MM&fecha_fin=AAAA-MM` | Puntos del mapa de ese periodo |
| Al elegir un mes | `GET /api/anomalias?departamento=PE-CUS&mes=AAAA-MM` | Detalle del mes (mediana, anomalía, margen, días) |
| Al dibujar un rectángulo | `GET /api/calendario?bbox=O,S,E,N&...` y `GET /api/focos.geojson?bbox=O,S,E,N&...` | Total y puntos del área |
| Botón CSV | `GET /api/hotspots.csv?<AOI>&fecha_inicio=AAAA-MM&fecha_fin=AAAA-MM` | Descarga de focos |
| Botón «En simple» | `GET /api/resumen?<AOI>` y `GET /api/analitica/{estacionalidad,ranking,acumulado,altitud}?<AOI>` | Cinco frases en lenguaje sencillo y cuatro gráficos descargables |
| Cambiar el año de la curva | `GET /api/analitica/acumulado?<AOI>&anio=AAAA` | Curva acumulada de ese año |

Ninguna llamada sale a FIRMS ni a Google: los datos son los CSV de Antonio, cargados en el servidor. Las únicas
conexiones externas del navegador son el mapa base (OpenFreeMap), la vista satelital (Esri) y las fuentes tipográficas.

### 2. Parámetros comunes

- **Idioma:** `lang=en|es` en cualquier ruta (por defecto `en`). La interfaz lo envía siempre según el selector
  EN | ES. Solo cambian los textos (`detail`, `notes`, `unidad`, frases); los campos y códigos no.

- **AOI (uno solo):** `departamento=PE-CUS` · `bbox=oeste,sur,este,norte` (grados WGS84, máx. 50 000 km²) ·
  `lat`, `lon` y `radio_km` (máx. 100 km). Debe tocar Cusco.
- **Fechas:** `AAAA-MM`, dentro de 2000-11 a 2025-12. En `/api/calendario` son opcionales (por defecto, toda la
  serie).

### 3. Respuestas

| Ruta | Campos principales |
| --- | --- |
| `/api/calendario` | `unidad{nombre, definicion}`, `anios`, `matriz_focos_armonizados[año][mes]`, `matriz_anomalia`, `total_focos_armonizados`, `cortes_color` (cuantiles 50/75/90/99), `celdas[]`, `notes[]` |
| celda de `celdas[]` | `anio`, `mes`, `sin_dato`, `focos_armonizados`, `celdas_dia`, `focos_modis`, `focos_viirs`, `mediana_hist`, `anomalia`, `categoria`, `calidad`, `fraccion_extrapolada`, `incertidumbre`, `rango[min,max]`, `anomalia_rango`, `fuente_serie`, `parcial` |
| `/api/anomalias` | los campos de la celda + `p25`, `p75`, `n_anios_hist`, `historial[{anio, focos_armonizados}]`, `dias[{fecha_local, focos_armonizados}]` |
| `/api/focos.geojson` | `FeatureCollection` de puntos con `fecha_local`, `hora_utc`, `sensor`, `satelite`, `eq_foco`, `en_serie`, `calidad` (sin FRP); `n_focos`, `total_focos_armonizados`. Máx. 50 000 focos por llamada |
| `/api/hotspots.csv` | CSV UTF-8 con BOM, **18 columnas del contrato** de Antonio; cabeceras `X-Row-Count` y `X-Total-Eq-Foco` |
| `/api/metadatos` | `unidad`, `armonizacion` (k, kT, margen, filtros), `cobertura`, `controles_maestro`, `creditos`, `notes` |
| `/api/resumen` | `titulo`, `frases[{pregunta, respuesta}]` (cinco), `notes` |
| `/api/analitica/*` | `titulo` (la pregunta), `en_simple` (respuesta en una frase), `como_leerlo`, y los datos del gráfico: `meses[]` (estacionalidad), `anios[]` y `anio_tipico` (ranking), `curva[]` y `rango_normal` (acumulado), `bandas[]` (altitud), `celdas[]` (recurrencia, con `limite`) |

Reglas de pantalla:
- El número que se muestra es `focos_armonizados`, con la etiqueta "Focos armonizados". En pantalla se puede
  redondear; en la descarga va sin redondear.
- `sin_dato: true` se muestra en gris y **nunca como 0**.
- Si la `calidad` es `extrapolado`, el mes va atenuado y con su `rango`.
- Si la `categoria` es `incierta`, la anomalía no se muestra como si fuera firme.
- Los focos MODIS y VIIRS se muestran por separado y no se suman.
- Las analíticas describen lo que ya ocurrió: no se rotulan como "riesgo", "alerta" ni "pronóstico". El "año típico"
  es la mediana de los años completos sin focos extrapolados (2003-2025). La recurrencia usa solo VIIRS (desde 2013).

### 4. Errores y límites (protocolo de solicitudes)

| Código | Cuándo | Qué hace la interfaz |
| --- | --- | --- |
| **422** | Consulta mal formada: AOI vacío, dos AOI a la vez, fecha mal escrita, rango invertido, área > 50 000 km², > 50 000 focos para el mapa, CSV > 200 000 filas | Muestra `detail` (texto en español) |
| **404** | **Sin datos:** otra región, área fuera de Cusco o fechas fuera de la serie | Muestra `detail`; nunca ceros |
| **429** | La misma IP superó **600 consultas nuevas/min** (ráfaga de 120) o **60 pesadas/min** (ráfaga de 20). Las respuestas repetidas de Cusco entero salen de la caché (`X-Cache: HIT`) y no gastan cupo | Esperar `Retry-After` segundos |
| **503** | Ya hay **4 consultas pesadas** en curso en el servidor y no se liberó turno en 8 s (o hay más de 16 esperando); o los datos no están cargados | Reintentar tras `Retry-After` |

- **Pesadas:** `/api/hotspots.csv` y cualquier llamada con `bbox` o `lat/lon`. Las de `departamento=PE-CUS` son
  livianas y se guardan en caché (~7 ms al repetirlas).
- **Cabeceras útiles:** `X-Process-Time-ms` (latencia), `X-RateLimit-Remaining` y `Retry-After`.
- **Estado:** `GET /health` (datos listos) y `GET /health/limits` (clientes y rechazos 429/503).
- Detrás de la nube se define `FIRECAL_TRUST_PROXY=1` para limitar por la IP real del visitante.

Ejemplo:
```
GET /api/calendario?departamento=PE-CUS&fecha_inicio=2020-01&fecha_fin=2020-12
-> 200 {"total_focos_armonizados": 1205.65, "celdas": [...], ...}
GET /api/calendario?departamento=PE-PUN
-> 404 {"detail": "Sin datos para 'PE-PUN': el prototipo solo tiene datos armonizados y validados de Cusco (PE-CUS)."}
```
Documentación interactiva (probar las llamadas desde el navegador): `http://localhost:8000/docs`.

## Revisión del PR de analíticas de Antonio (sáb 14 nov 2026, noche)

`antonio/analitica` unido a esta rama (sin conflictos). Verificado: 151 pruebas, ESLint y build, `verificar_datos.py`
TODO OK, frases con los datos reales, sin FRP ni "riesgo/alerta", panel "En simple" probado en el navegador.
Correcciones aplicadas en la revisión:
- [x] Fecha de la frase de la curva en **años bisiestos** (salía un día después: 2020 cruzó el 24 de agosto, no el 25).
- [x] **Nota de 2025** (MAESTRO P2) en la curva, el ranking y el resumen; el panel ahora muestra todas las notas.
- [x] El panel muestra "Calculando…" al cambiar de área, en vez de los datos anteriores.
- [x] Una prueba de límites dependía de tener la interfaz compilada.

## Publicado en Google Cloud Run (sáb 14 nov 2026, ~17:15)

- **URL pública:** https://firecal-316891526626.southamerica-east1.run.app (API en `/api/*`, documentación en `/docs`).
- Proyecto `sonic-mile-514718-r5`, región São Paulo, 1 GB, 1 instancia mínima y 2 como máximo, imagen
  `firecal-cusco:8fc1f2b` en Artifact Registry. Casos de MAESTRO §12 comprobados contra la URL pública.
- Variables: `FIRECAL_TRUST_PROXY=1` y `FIRECAL_PROXY_HOPS=1`. Comprobado en producción: Cloud Run agrega al final de
  `X-Forwarded-For` solo la IP real del visitante. Las revisiones 2 y 3 quedaron mal configuradas (2 saltos y, luego, una
  variable mal guardada por la coma en PowerShell); la revisión 5 lo corrige.
- PR #8 unido a `main` (b5768dd).
- [ ] Probar el límite con dos personas en redes distintas.
- [ ] Al terminar la evaluación: `--min-instances 0` o borrar el servicio.

## Auditoría de Gabriel (resto) + nueva interfaz de Dante (sáb 14 nov 2026, noche)

Publicado como revisión **`firecal-00006`** (imagen `firecal-cusco:dante-v1`). Comprobado en la URL pública: casos de
MAESTRO (2005 = 1355, 2020 = 1206), PE-PUN → 404, gzip, caché de 1 h, `nosniff` y una sola IP contada aunque se
falsifique `X-Forwarded-For`. Detalle, recomendaciones, seguridad y costos: `CAMBIOS_Y_RECOMENDACIONES.md`.

**Backend**
- [x] Retirado el backend sintético (66 % del código: simulador, H3, `/api/v1`, LightGBM). Archivado en la rama
      `archivo/backend-sintetico`. Imagen: 1,33 GB → 917 MB; dependencias: 60 → 47.
- [x] `firecal` solo tiene `plan-events` y `serve`.

**Cambios en el protocolo de llamadas**
- [x] `GET /api/resumen?graficos=true`: frases y datos de los 4 gráficos en **una** llamada. Antes eran 5.
- [x] Parámetro desconocido (p. ej. `departmento`) → **422** con la lista de válidos. Antes respondía "área vacía".
- [x] Fechas solo `AAAA-MM`: `2020-8` o `2020-01-15` → 422.
- [x] Consultas pesadas, si hay área dibujada (`bbox`/`lat`): calendario, anomalías, focos.geojson, resumen y
      `analitica/*`; además `hotspots.csv` siempre.
- [x] Área dibujada: título legible ("the selected area") y coordenadas en `aoi.bbox`.

**Interfaz (rama de Dante, b4dbf8c, adaptada)**
- [x] Mapa base con relieve, logo del equipo, barra superior derecha (EN/ES y ayuda) y nueva línea de tiempo.
- [x] El botón "Hotspots" del riel centra Cusco y abre el detalle; leyenda de la capa de puntos.
- [x] Calendario: años recientes primero, uso con teclado (Tab, Enter) y cerrado por defecto en pantallas < 1600 px.
- [x] La tarjeta de selección ya no tapa el panel "En simple"; riel horizontal en el celular.
- [x] Se rotulan los dos conteos: armonizados frente a "detecciones en el mapa (sin ponderar)".

## QA de Erik (rama `erik/qa`) aplicado (sáb 14 nov 2026, noche)

Revisión **`firecal-00008`** (imagen `firecal-cusco:qa-erik-v2`). La rama de Erik (`QA_ERIK.md` y `qa/`) quedó unida.
El estado de cada uno de los 14 errores está al final de `QA_ERIK.md`.
- [x] API: fechas recortadas a 2000-2025, mensajes de validación en el idioma de la persona, radio 0, "mes
      inválida" y área sin fuego con un mensaje claro.
- [x] "En simple": áreas con poco fuego, año más tranquilo nunca extrapolado y plurales.
- [x] Interfaz: el ▶ salta los meses sin dato, sin jerga técnica, botones con nombre y escala de años con flechas
      fijas (se cortaba en 2021).
- [x] 90 pruebas en verde (7 nuevas `test_qa_erik_*`).
- [ ] Probar en un teléfono real y dibujar un área con el dedo.

## Capacidad de Gabriel + panel de Dante (sáb 14 nov 2026, noche)

Revisión **`firecal-00009`** (imagen `firecal-cusco:gabriel-dante-v1`).
- [x] Rama `gabriel2` unida (AUDITORIA.md §10): datos en tablas en memoria, caché de respuestas de Cusco entero,
      cupos por IP pensados para una sala con la misma IP y carril de pesadas con fila máxima. Revisado: la caché
      separa idiomas (`?lang`) y gzip, tiene tope de memoria, y lo que no sale de la caché sigue pasando por los
      límites. Comprobado en la URL: `X-Cache: HIT` y la IP falsificada se ignora.
- [x] Dante (450cc43, 2dad4eb): relieve por defecto y panel de fondo y leyenda abajo a la derecha. Adaptado: sin
      FRP, en inglés y español, con los colores reales de la capa y la leyenda de puntos. La línea de tiempo se
      acomoda para no chocar con el panel.
- [x] El error de red ("La API respondió con estado…") sale en el idioma elegido.
- [x] Análisis preventivo con Meteomatics: el clima no anticipa el fuego
      (`exploratorio/meteomatics/resultados/PREVENTIVO.md`).
- [ ] Decidir la configuración de Cloud Run que sugiere Gabriel (ver `CAMBIOS_Y_RECOMENDACIONES.md`).

## Tiempo real con la MAP_KEY de FIRMS (sáb 14 nov 2026, noche)

- [x] `GET /api/tiempo-real?horas=24|48|120` (`firecal/nrt.py`): detecciones NRT de las 4 fuentes de FIRMS, recortadas
      al contorno de Cusco. El servidor las pide cada 15 min y las comparte con todos (~16 transacciones por hora
      frente al límite de 5000 cada 10 min). Si FIRMS falla, se muestra lo último con aviso. Sin FRP.
- [x] Es una capa aparte de la serie armonizada: cada punto es una detección cruda y no se suma al calendario
      (MAESTRO).
- [x] La clave solo vive en el servidor: no llega al navegador, no queda en los logs (`httpx` registraba la URL con la
      clave; ahora se redacta) ni en los errores. 7 pruebas nuevas con FIRMS simulado (110 en verde).
- [x] Interfaz: botón **En vivo** en la barra lateral, panel con ventana de 24 h, 48 h o 5 días, color por
      antigüedad, detalle al hacer clic y renovación cada 5 min.
- [x] Publicado en la revisión **`firecal-00010`** (imagen `firecal-cusco:live-v1`). La MAP_KEY está en Secret
      Manager (`firms-map-key`) y solo la cuenta de servicio de Cloud Run puede leerla
      (`roles/secretmanager.secretAccessor` sobre ese secreto). Comprobado en la URL: 11 detecciones en 24 h y 23 en
      5 días en Cusco, las 4 fuentes responden, y la clave no aparece en las respuestas ni en los logs.
- Para cambiar la clave: `gcloud secrets versions add firms-map-key --data-file=<archivo>` y volver a desplegar.
- [x] Revisión **`firecal-00011`**: el histórico y el tiempo real son **dos modos separados** (selector "Serie
      histórica | En vivo" arriba a la izquierda). En vivo se ocultan la densidad, los puntos, el resumen, el
      calendario, la línea de tiempo, "En simple" y el área dibujada; la leyenda muestra la antigüedad. Al volver, el
      histórico queda como estaba.

## Orden de la interfaz (dom 15 nov 2026)

Revisión **`firecal-00016`**.
- [x] El panel "Focos armonizados" (Info) empieza cerrado y solo se abre con el botón **Info** (o con "?").
- [x] **Área:** centra Cusco con más zoom, cierra los paneles y oculta la línea de tiempo mientras se dibuja; al
      terminar aparecen la tarjeta del área y la línea de tiempo (día, mes y año).
- [x] **Un solo panel a la vez** (Info, Calendario, En simple o la tarjeta del área): abrir uno cierra el otro.
- [x] Sin superposiciones: auditoría automática en la URL pública (7 pasos × 3 anchos: 1440, 1100 y celular) sin
      ningún choque entre paneles, barra lateral, barra superior, selector de modo, línea de tiempo, fondo y capas.

## Pendientes que me afectan

- [x] Datos reales de FIRMS (Cusco, de Antonio).
- [x] Departamentos del AOI: solo Cusco (decisión del equipo).
- [ ] Límite de latencia (ms) para la selección de muestras.
- [ ] Objetivo de latencia para pruebas con APIs grandes y cómo se mide.
- [ ] Umbral de confianza (hoy `nominal`; se expone en `/api/metadatos`).
- [ ] Si GeoServer entra o se sirve GeoJSON desde FastAPI (hoy: GeoJSON desde FastAPI).
- [ ] Antes de publicar: mapa base con clave propia, 1 réplica mínima, monitoreo y reducir el tamaño de la imagen.
