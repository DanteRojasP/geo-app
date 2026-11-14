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

## Pendientes que me afectan

- [ ] Límite de latencia (ms) para la selección de muestras.
- [ ] Objetivo de latencia para pruebas con APIs grandes y cómo se mide.
- [ ] Umbral de confianza (se expone en `/api/metadatos`).
- [ ] Si GeoServer entra o se sirve GeoJSON desde FastAPI.
