# FireCal Cusco: plataforma local (guía)

Prototipo del reto *Calendario de incendios armonizado (MODIS + VIIRS)*, NASA Space Apps 2026.
Une tres piezas del equipo:

| Pieza | Autor | Qué aporta |
| --- | --- | --- |
| `PLAN.md` | equipo | Alcance, endpoints y cronograma |
| `MAESTRO.md` + `data/harmonized/` + `harmonizacion/` | Antonio | **Datos reales de NASA FIRMS para Cusco ya armonizados** (2000-11-04 a 2025-12-31), contratos y verificación |
| `plataforma_local/` (esta carpeta) | Julio | Backend FastAPI + DuckDB, frontend Leaflet, Docker y protocolo de solicitudes |

> **Alcance del prototipo: solo Cusco** (decisión del equipo, MAESTRO §12). Es la única región con factores de
> armonización validados. Cualquier otra región o fecha fuera de 2000-11-04 a 2025-12-31 responde **"sin datos"**
> (nunca ceros). Es una serie **histórica**: no incluye 2026.

Antes de tocar datos o armonización, lee [`../MAESTRO.md`](../MAESTRO.md).

---

## 1. Qué muestra

- **Unidad: "Focos armonizados"** (*harmonized hotspots*): celdas de ~1 km con fuego por día, en escala equivalente
  a MODIS. Combina MODIS (2000–2012) y VIIRS (2013 en adelante). Es la suma de `eq_hotspots` (celda-día) o de
  `eq_foco` (focos). Nunca se cuentan filas ni se suma `n_modis + n_viirs`.
- **No se usa el FRP** (no está armonizado entre sensores) y **no se calcula área quemada**. Tampoco se habla de
  "eventos": los datos son focos (*hotspots*).
- **Calendario mes × año** con rampa YlOrRd de 6 clases. Los cortes son los cuantiles 50/75/90/99 de los meses con
  fuego de la selección actual. El cero va en gris neutro y "sin dato" en gris rayado. Los meses `extrapolado`
  (2000-11 a 2002-07, solo Terra) se ven atenuados y rayados. Hay una nota explicativa para 2025.
- **Modo anomalía** (alternativa C del PLAN): `(valor − mediana del mismo mes) / max(IQR, 1)`.
- **Detalle por mes:** valor, celdas-día, focos MODIS y VIIRS por separado, calidad, barras por día y el mismo mes en
  otros años.
- **Descarga CSV** con las **18 columnas del contrato** de Antonio. El total que muestra la web es igual a
  Σ `eq_foco` del archivo descargado.

## 2. Estructura en el repositorio (rama `julio/actividades`)

```
MAESTRO.md                      contexto, reglas y contratos (Antonio)
data/harmonized/                CSV armonizados de Cusco (fuente de verdad)
harmonizacion/                  scripts de Antonio + cusco_ref/ (límite FAO GAUL y altitud)
plataforma_local/
├── backend/
│   ├── firecal/plan/sources.py   dónde están los CSV, contrato de columnas y sumas de control
│   ├── firecal/plan/events.py    CSV -> Parquet (anio/mes) + validación contra MAESTRO §6
│   ├── firecal/plan/query.py     calendario, anomalía, AOI y descarga (DuckDB)
│   ├── api/routers/plan.py       GET /api/...
│   ├── api/limits.py             protocolo de solicitudes (429/503, candados)
│   └── tests/test_plan.py        casos de prueba de MAESTRO §12 y del plan
├── frontend/                     index.html + app.js + app.css + Leaflet local
├── Dockerfile, docker-compose.yml
└── docs/                         despliegue/falencias y beneficios NASA
```

El backend busca los datos en la raíz del repositorio (`../../data/harmonized`). Otra ubicación se indica con
`FIRECAL_SOURCE_ROOT`.

---

## 3. Cómo ejecutarla

### Opción A: Docker (recomendada)

Requiere Docker Desktop abierto. Desde `plataforma_local/`:
```powershell
docker compose up --build          # ~1,5 min la primera vez; luego abre http://localhost:8000
```
La construcción valida los CSV contra MAESTRO §6: si los datos cambiaron, falla y no publica nada.
Imagen de 1,32 GB; el contenedor usa ~170 MB de RAM.

### Opción B: Python (para desarrollar)

PowerShell, desde `plataforma_local/backend`:
```powershell
py -3.12 -m venv .venv                                         # solo la primera vez
.\.venv\Scripts\python -m pip install -r requirements-lock.txt # solo la primera vez
.\.venv\Scripts\python -m pip install -e . --no-deps           # solo la primera vez
$env:PYTHONUTF8 = "1"
.\.venv\Scripts\firecal plan-events     # ~2 s: valida los CSV y arma el Parquet
.\.venv\Scripts\firecal serve           # http://localhost:8000  (API: /docs)
```
Pruebas: `.\.venv\Scripts\python -m ruff check .` y `.\.venv\Scripts\python -m pytest -q` (136 pruebas).

Verificación de los datos (script de Antonio, ahora funciona en Windows), desde la raíz del repo:
```powershell
python -I harmonizacion/verificar_datos.py data/harmonized/harmonizado_cusco_celda_dia.csv data/harmonized/focos_cusco_individuales.csv
```

---

## 4. Endpoints (contrato Julio ↔ Dante)

AOI: `departamento=PE-CUS` **o** `bbox=oeste,sur,este,norte` **o** `lat=..&lon=..&radio_km=..` (dentro de Cusco).

| Ruta | Parámetros | Devuelve |
| --- | --- | --- |
| `GET /api/departamentos` | — | Cusco (único con datos) y su límite en GeoJSON |
| `GET /api/calendario` | AOI, `fecha_inicio`, `fecha_fin` (AAAA-MM, opcionales) | `anios`, `matriz_eq_hotspots` y `matriz_anomalia` (años × 12), `total_eq_hotspots`, `cortes_color`, `celdas[]` |
| `GET /api/anomalias` | AOI, `mes` | valor del mes, mediana e IQR del mismo mes, anomalía, `historial[]` y `dias[]` |
| `GET /api/hotspots.csv` | AOI, `fecha_inicio`, `fecha_fin` | CSV de focos (18 columnas del contrato, UTF-8 con BOM); cabeceras `X-Row-Count` y `X-Total-Eq-Foco` |
| `GET /api/metadatos` | — | unidad, método (k, kT, calidad), cobertura, sumas de control y créditos |
| `GET /health`, `GET /health/limits` | — | estado de los datos y del protocolo de solicitudes |

Celda del calendario: `{anio, mes, sin_dato, eq_hotspots, celdas_dia, focos_modis, focos_viirs, mediana_hist,
anomalia, categoria, calidad, fuente_serie, parcial}`.

Errores: **404 "Sin datos"** (otra región, área fuera de Cusco o fechas fuera de la serie); **422** con el motivo
(AOI vacío, rango invertido, fecha mal escrita, área demasiado grande, CSV de más de 200 000 filas); **429/503**
del protocolo de solicitudes, con `Retry-After`.

Ejemplo:
```powershell
Invoke-RestMethod "http://localhost:8000/api/calendario?departamento=PE-CUS&fecha_inicio=2020-01&fecha_fin=2020-12"
```

El backend anterior con datos sintéticos (`/api/v1`, 5 departamentos) quedó **desactivado**
(`settings.yaml → api.legacy_v1: false`). Solo sirve como referencia de la alternativa B.

---

## 5. Casos de prueba de MAESTRO §12 (todos pasan)

| Consulta | Esperado | Obtenido |
| --- | --- | --- |
| Todo el periodo | 15 732 (36 260 celdas-día; 58 779 focos en la descarga) | 15 732,03 · 36 260 · 58 779 |
| 2005 / 2012 / 2013 / 2020 / 2025 | 1355 / 678 / 424 / 1206 / 385 | iguales (±1) |
| Antes de 2000-11-04, o fuera de Cusco | "sin datos" (no cero) | 404 "Sin datos" |
| Σ `eq_foco` de la descarga | = total en pantalla | igual para departamento, rectángulo y punto |

---

## 6. Procedimiento seguido (registro)

1. Clonar el backend de pruebas (`project_nasa`, rama `backend`) y adaptarlo al PLAN (14-nov): departamentos,
   endpoints GET, frontend, Docker y protocolo de solicitudes.
2. Integrar el trabajo de Antonio (14-nov): `git merge origin/antonio/modelo` en `julio/actividades` (sin conflictos).
3. Corregir `harmonizacion/verificar_datos.py` para Windows: la consola cp1252 no imprime `Δ` y `python -I` ignora
   `PYTHONUTF8`. Ahora el script reconfigura su salida a UTF-8. Registrado en MAESTRO §7 y §11.
4. Reemplazar los datos sintéticos por los CSV de Antonio (`firecal/plan/`), con validación contra MAESTRO §6.
5. Aplicar las decisiones del equipo: solo Cusco, unidad "focos armonizados", sin FRP y sin la palabra "evento".
6. Rehacer el frontend según MAESTRO P2/P3 (rampa YlOrRd por cuantiles, extrapolado atenuado, CSV de 18 columnas).
7. Docker con los datos como contexto adicional; validación en la construcción.

## 7. Pendientes

- [ ] Analíticas descargables de MAESTRO P4 (serie anual por fuente, perfil estacional, bandas de altitud).
- [ ] Vista diaria del calendario completo (hoy el detalle diario está en el panel de cada mes).
- [ ] `harmonizacion/sequia_fuego/n_efectivo_potencia.py` tiene el mismo problema de Windows con `≈` (no se tocó).
- [ ] Antes de publicar: ver [`docs/DESPLIEGUE_Y_FALENCIAS.md`](docs/DESPLIEGUE_Y_FALENCIAS.md).
