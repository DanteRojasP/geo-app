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

| Endpoint | Entrada | Salida |
|---|---|---|
| `GET /api/calendario` | AOI (departamento de Perú; alternativa: bbox o centro + radio), fecha inicio y fin | Matriz mes × año |
| `GET /api/anomalias` | AOI y mes consultado | Comparación con la mediana histórica |
| `GET /api/hotspots.csv` | AOI y rango de fechas | CSV de eventos del rango |
| `GET /api/metadatos` | — | Versión del armonizador, umbral de confianza y advertencias |

Formatos de referencia:
- **Evento armonizado:** `fecha_utc, hora, lat, lon, celda_1km, sensor, confianza_norm (0–1), frp_mw, dia_noche`
- **Agregado mensual:** `anio, mes, n_eventos, frp_total, mediana_hist, anomalia`
- **Hacia la web:** JSON; GeoJSON solo para el AOI y puntos de rangos pequeños.

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
  - B (calibración por solapamiento) sigue disponible en `/api/v1` (backend anterior).
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
  - El backend sintético anterior (`/api/v1`, 5 departamentos) quedó apagado.
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

## Pendientes que me afectan

- [x] Datos reales de FIRMS (Cusco, de Antonio).
- [x] Departamentos del AOI: solo Cusco (decisión del equipo).
- [ ] Límite de latencia (ms) para la selección de muestras.
- [ ] Objetivo de latencia para pruebas con APIs grandes y cómo se mide.
- [ ] Umbral de confianza (hoy `nominal`; se expone en `/api/metadatos`).
- [ ] Si GeoServer entra o se sirve GeoJSON desde FastAPI (hoy: GeoJSON desde FastAPI).
- [ ] Antes de publicar: mapa base con clave propia, 1 réplica mínima, monitoreo y reducir el tamaño de la imagen.
