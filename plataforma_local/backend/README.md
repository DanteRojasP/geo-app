# Backend de Nikal Cusco

API FastAPI + DuckDB que sirve los datos armonizados de Cusco (`MAESTRO.md`, `data/harmonized/`) y la interfaz
compilada (`../frontend/dist`). La guía completa (instalación, endpoints, protocolo, despliegue) está en
[`../README.md`](../README.md).

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-lock.txt
.\.venv\Scripts\python -m pip install -e . --no-deps
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\firecal plan-events      # valida los CSV contra MAESTRO §6 y arma el Parquet (~2 s)
.\.venv\Scripts\firecal serve            # http://localhost:8000  (API en /api, documentación en /docs)
.\.venv\Scripts\python -m pytest -q      # 83 pruebas
```

| Carpeta | Contenido |
| --- | --- |
| `firecal/plan/` | `sources.py` (contrato y sumas de control), `events.py` (CSV → Parquet), `query.py` (calendario, anomalía, AOI, descargas), `analitica.py` (analíticas "en simple") |
| `firecal/i18n.py` | Textos en inglés y español (`?lang=en|es`) |
| `api/routers/plan.py` | Rutas `GET /api/...` |
| `api/limits.py` | Protocolo de solicitudes (429/503, candados) |
| `tests/` | Casos de MAESTRO §12, analíticas, idiomas y límites |

**Historia:** el backend sintético anterior (simulador, armonización por razón, H3, `/api/v1`, 5 departamentos) se
retiró el 14-nov-2026 por recomendación de la auditoría de Gabriel. Era el 66 % del código y no lo usaba la app.
Está completo en la rama **`archivo/backend-sintetico`**.
