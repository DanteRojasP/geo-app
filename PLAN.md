# Plan de trabajo: Calendario de incendios armonizado (MODIS + VIIRS)

NASA Space Apps Challenge 2026 · Equipo de 5 personas · Sáb 14 nov 9:00 – Dom 15 nov 23:59 (≈38 h)

## 1. Reto

Construir una aplicación web que combine los *hotspots* de FIRMS de MODIS (desde 2000) y VIIRS (desde 2012) en una serie consistente, para que el cambio de sensor no se vea como un cambio en el fuego.

- El usuario elige un área de interés (AOI) y un rango de fechas.
- Obtiene un calendario de actividad (meses × años), conteos de hotspots, comparación con la mediana histórica (anomalías) y un CSV descargable.
- Público: equipos de emergencia, científicos, gestores de tierras y brigadistas.
- **Alcance geográfico (AOI):** los departamentos de Perú con más incendios históricos, a nivel departamental.

## 2. Decisiones de armonización

- **Responsable:** Antonio.
- **Alternativas del MVP:** **A (grilla común de 1 km) + C (anomalías normalizadas)**.
- **Alternativa B (calibración por solapamiento 2012+):** opcional. Solo se incorpora si el hito H1 (sáb 20:00) se cumple a tiempo.
- **Regla de deduplicación:** si MODIS y VIIRS detectan en la misma celda de 1 km el mismo día, cuenta como un solo evento y se conserva el de mayor FRP (MW).
- **Umbral de confianza:** por definir (ver sección 9).
- **Latencia (requisito):** máximo en milisegundos para la selección de imágenes de muestra. Las pruebas con APIs grandes tienen un objetivo distinto y se miden aparte (ver sección 9).

## 3. Formatos

- **Entrada:** CSV de FIRMS (descarga por región y periodo).
- **Almacenamiento:** Parquet particionado por año y mes; se consulta con DuckDB o pandas.
- **Evento armonizado:** `fecha_utc, hora, lat, lon, celda_1km, sensor, confianza_norm (0–1), frp_mw, dia_noche`.
- **Agregado mensual por AOI:** `anio, mes, n_eventos, frp_total, mediana_hist, anomalia`.
- **Hacia la web:** JSON desde la API; GeoJSON solo para el AOI y puntos de rangos pequeños.

## 4. Arquitectura

**Opción 1 (elegida): FastAPI + Parquet + Leaflet.**
- Backend en FastAPI sobre Parquet con DuckDB.
- Frontend con Leaflet (dibujo del AOI con Leaflet.draw) y calendario de calor mes × año con escala viridis/cividis.
- GeoServer es opcional, solo para publicar la capa de puntos como WMS/WFS.

**Endpoints mínimos (contrato entre Julio y Dante):**
- `GET /api/calendario`: AOI (departamento de Perú; alternativamente bbox o centro + radio), fecha inicio y fin → matriz mes × año.
- `GET /api/anomalias`: mes consultado frente a la mediana histórica.
- `GET /api/hotspots.csv`: descarga de eventos del rango seleccionado.
- `GET /api/metadatos`: versión del armonizador, umbral de confianza y advertencias.

## 5. Roles

| Integrante | Rol | Entregables | Depende de |
|---|---|---|---|
| **Julio** | Backend | API FastAPI con los 4 endpoints; carga de Parquet; exportación CSV; documentación OpenAPI | Antonio (esquema congelado a las 11:00 del sáb) |
| **Dante** | Frontend y geoservidor | Mapa Leaflet, selector de AOI por departamento (dibujo opcional), selector de fechas, calendario en color; integración con GeoServer u opción GeoJSON | Julio (contrato de la API); empieza con datos de muestra |
| **Antonio** | Armonización | Ingesta de FIRMS, normalización de confianza, grilla de 1 km, deduplicación, anomalías y diccionario de datos | Ninguno. Cuello de botella: prioridad máxima |
| **Erik** | Q/A de usuario, propuesta y control de errores | Casos de uso reales; mensajes de error claros (AOI vacío, rango invertido, sin datos, área demasiado grande); revisión de UX y de la propuesta | Frontend y API integrados (H2) |
| **Gabriel** | Q/A de lógica | Pruebas de conteos, deduplicación, mediana y anomalías contra un cálculo manual en un caso de control; validación del CSV | Datos armonizados v1 (H1) |

## 6. Cronograma y hitos

| Bloque | Qué se hace | Hito |
|---|---|---|
| Sáb 14 · 9:00–11:00 | Kickoff: alcance del MVP, AOI de prueba (región con historial de incendios), esquema ligero | **Esquema congelado (11:00)** |
| Sáb 14 · 11:00–17:00 | Antonio ingiere y armoniza. Julio arma la API con datos de muestra. Dante hace el mapa base. Erik y Gabriel escriben los casos de prueba | |
| Sáb 14 · 17:00–20:00 | Dataset armonizado v1 y endpoint `/calendario` con datos reales | **H1 (20:00)** |
| Dom 15 · 9:00–13:00 | Integración API ↔ frontend; anomalías; descarga CSV; calendario conectado | **H2 (13:00)**: flujo completo en el AOI de prueba |
| Dom 15 · 13:00–17:00 | QA ronda 1 (Erik en usuario, Gabriel en lógica) y correcciones | **H3 (17:00)**: sin errores críticos |
| Dom 15 · 17:00–21:30 | Pulido visual, texto de metodología, créditos de FIRMS, README y capturas | |
| Dom 15 · 21:30–23:59 | Congelar código, revisar versión final y entregar | **H4 (21:30)**: code freeze · **entrega (23:59)** |

## 7. Alcance

**MVP (obligatorio):**
- Selección del AOI por departamento de Perú (dibujo en el mapa como opción adicional).
- Rango de fechas.
- Calendario mes × año con escala de color accesible.
- Conteo mensual y comparación con la mediana histórica.
- Descarga CSV de los hotspots del rango.
- Nota de metodología y créditos: "We acknowledge the use of data and/or imagery from NASA's FIRMS".

**Extras (si hay tiempo):**
- Capa WMS publicada en GeoServer.
- Comparación de un incendio actual con su historial.
- Mapa de puntos filtrado por fecha.
- Calibración por solapamiento (alternativa B), si no quedó en el MVP.

## 8. Riesgos y mitigación

| Riesgo | Mitigación |
|---|---|
| Cuello de botella en la armonización (Antonio) | Esquema congelado a las 11:00; frontend y API trabajan con datos de muestra |
| Límites o lentitud en la descarga de FIRMS | Archivos por región y periodo acotado. Si se usa la API, tramitar la clave MAP_KEY al inicio |
| Volumen global de datos demasiado grande | Recortar al AOI y a un periodo corto; trabajar siempre en Parquet |
| GeoServer toma demasiado tiempo | Servir GeoJSON desde FastAPI y dejar GeoServer como extra |
| Pocos años de historia en una zona | Mostrar un aviso y no calcular anomalías con menos de unos 5 años (por validar) |
| Umbral de confianza sin justificar | Documentar el umbral elegido y su motivo en la sección de metodología de la app |

## 9. Decisiones pendientes (confirmar hoy)

- [ ] Departamentos de Perú que entran al AOI (los de mayor historial de incendios) y el departamento de prueba (sáb 9:00).
- [ ] Umbral de confianza para MODIS y para las categorías de VIIRS.
- [ ] Si GeoServer entra en la versión final o queda como extra.
- [ ] Si la elección del sensor se hace por fecha (VIIRS desde 2012) o por deduplicación en todo el periodo.
- [ ] **Límite de latencia en ms** para la selección de imágenes de muestra (valor exacto por definir).
- [ ] **Objetivo de latencia para pruebas con APIs grandes** (distinto del de muestra; definir valor y cómo se mide).
- [ ] Verificar contra la guía de atributos de FIRMS los umbrales, la fecha de inicio de VIIRS y los nombres de campos antes de fijar el esquema.
