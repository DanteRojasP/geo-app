# CLAUDE.md — FireCal Cusco (backend)

**Antes de tocar datos o armonización, lee `MAESTRO.md` (raíz del repositorio).**

## Reglas
- Comunicar en español neutro; mensajes al usuario en español e inglés con `firecal.i18n.t(es=..., en=...)`.
- Reglas del equipo (MAESTRO §1 y §12): solo Cusco; unidad "focos armonizados" (campo `focos_armonizados` = Σ
  `eq_hotspots` / Σ `eq_foco`); no contar filas; no usar FRP; no usar "evento", "riesgo" ni "alerta"; fuera de
  cobertura = "sin datos" (404), nunca 0. Las analíticas describen; no son pronósticos.
- No subir credenciales (`*credenciales*`, `.env`) ni datos de Meteomatics.
- Cada cambio: `ruff check .` y `pytest -q` en verde.

## Estructura
- `firecal/plan/sources.py`: rutas de los CSV (`FIRECAL_SOURCE_ROOT`), contrato y sumas de control (MAESTRO §6).
- `firecal/plan/events.py`: `firecal plan-events` → `data/processed/plan/{celda_dia,focos}/anio=/mes=` +
  `cusco_limite.geojson` + `plan_meta.json`. Falla (`DataContractError`) si los datos no coinciden.
- `firecal/plan/query.py`: `PlanStore` (tablas de DuckDB en memoria, no vistas sobre el Parquet; caché por AOI con
  `SingleFlight`). Departamento →
  celda-día; bbox/punto → focos por latitude/longitude. Margen de extrapolados (Antonio): 41 %/45 % por estrato.
  Fechas solo `AAAA-MM`.
- `firecal/plan/analitica.py`: estacionalidad, ranking, acumulado, altitud, recurrencia y resumen (`graficos=1`).
- `firecal/plan/ambitos.py`: nivel de peligro por focos de calor (formato CENEPRED) por provincia, distrito y
  cuenca Pfafstetter (`config/ambitos/`, `scripts/build_ambitos.py`), informes HTML; rutas en `api/routers/ambitos.py`;
  `firecal informes` los genera en lote. Peligro relativo, sin vulnerabilidad: no llamarlo de otra forma.
- `api/routers/plan.py`: rutas `GET /api/...`; parámetros desconocidos → 422 (`KNOWN_PARAMS`).
- `api/cache.py`: caché de respuestas completas de Cusco entero (`X-Cache: HIT`); lo repetido no gasta cupo.
- `api/limits.py`: 600 consultas nuevas/min por IP, 60 pesadas/min, 4 pesadas a la vez (8 s de espera). Detrás de Cloud Run:
  `FIRECAL_TRUST_PROXY=1`, `FIRECAL_PROXY_HOPS=1` (Cloud Run agrega solo la IP real; comprobado en producción).
- `api/main.py`: idioma por solicitud, GZip, Cache-Control (1 h para `/api`), `nosniff`, interfaz desde
  `../frontend/dist`.

## Historia
El backend sintético (Fases 0-6: simulador, H3, armonización por razón, `/api/v1`) está en la rama
`archivo/backend-sintetico`.
