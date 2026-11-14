# FireCal Cusco: plataforma local (guía)

Prototipo del reto *Calendario de incendios armonizado (MODIS + VIIRS)*, NASA Space Apps 2026.
Une el trabajo del equipo con `PLAN.md` (en `main`) como eje:

| Pieza | Autor | Qué aporta |
| --- | --- | --- |
| `PLAN.md` | equipo | Alcance, endpoints y cronograma |
| `MAESTRO.md` + `data/harmonized/` + `harmonizacion/` | Antonio | **Datos reales de NASA FIRMS para Cusco ya armonizados** (2000-11-04 a 2025-12-31), contratos, verificación y margen de los meses extrapolados |
| `frontend/` | Dante (adaptado) | Interfaz "Firewatch Perú" (React + Vite + MapLibre) conectada a nuestra API |
| `backend/`, Docker, protocolo de solicitudes | Julio | API FastAPI + DuckDB, imagen Docker (basada en la de Antonio) y límites 429/503 |

> **Alcance: solo Cusco** (MAESTRO §12). Es la única región con armonización validada. Otra región, un área fuera
> de Cusco o fechas fuera de 2000-11-04 a 2025-12-31 responden **"sin datos"** (nunca ceros). Serie **histórica**:
> no incluye 2026. Antes de tocar datos o armonización, lee [`../MAESTRO.md`](../MAESTRO.md).

---

## 1. Qué muestra

- **Unidad: "Focos armonizados"** (*harmonized hotspots*): celdas de ~1 km con fuego por día, en escala equivalente
  a MODIS. En la API el campo se llama **`focos_armonizados`** (decisión del equipo). Es la suma de `eq_hotspots`
  (celda-día) o de `eq_foco` (focos): nunca se cuentan filas ni se suma `n_modis + n_viirs`.
- **Sin FRP** (no está armonizado entre sensores), **sin área quemada** y **sin "eventos"**: los datos son focos.
- **Interfaz (base de Dante):** mapa MapLibre a pantalla completa con Cusco resaltado y el resto atenuado.
  - **Capas:** densidad (mapa de calor pesado por `eq_foco`), focos (puntos por sensor), límite y área.
  - **Panel de resumen:** focos armonizados, mediana, anomalía y focos MODIS/VIIRS por separado.
  - **Selección de área** con vista satelital (Esri) y su propio total y descarga.
  - **Barra inferior:** año y sus 12 meses; el botón ▶ recorre los meses.
- **Calendario mes × año** (eje del PLAN):
  - Rampa YlOrRd con cortes en los cuantiles 50/75/90/99 de los meses con fuego.
  - El cero va en gris; "sin dato", rayado.
  - Los meses **extrapolados** (2000-11 a 2002-06, solo Terra) aparecen atenuados y con su **margen**.
  - Anomalía **"incierta"** (borde punteado) cuando el margen cruza de categoría.
  - Modo anomalía: `(valor − mediana del mismo mes) / max(IQR, 1)`.
- **Margen de los extrapolados (método de Antonio):** `incertidumbre` = 41 % (≥ 2500 m) o 45 % (< 2500 m) de los
  focos armonizados extrapolados (error mensual de kT, MAESTRO §7). De ahí salen `rango` y `anomalia_rango`.
- **Descarga CSV** con las **18 columnas del contrato** de Antonio; el total en pantalla es igual a Σ `eq_foco` del
  archivo.

## 1b. Idiomas (i18n)

- **Inglés por defecto**; español con el selector **EN | ES** de la barra superior o con `?lang=es` en la URL (la
  elección se guarda en el navegador).
- **API:** parámetro `?lang=en|es` en todas las rutas (por defecto `api.default_lang: en`). Se traducen los textos
  libres: `detail` de los errores, `notes`, `unidad`, `titulo`, `en_simple`, `como_leerlo` y los textos de
  `/api/metadatos`. **No se traducen** los nombres de campos ni los códigos (`categoria`, `calidad`, `veredicto`,
  `fuente_serie`): son el contrato con la interfaz.
- **Código:** `backend/firecal/i18n.py` (`t(es=..., en=...)`, idioma por solicitud) y `frontend/src/i18n.js`
  (diccionarios `en`/`es`, función `tr`).
- **Agregar un idioma** (p. ej. portugués o quechua):
  - En la interfaz basta con un diccionario nuevo en `i18n.js`.
  - En la API hay que pasar `pt="..."` en cada `t(...)`, unos 80 textos. Las frases de las analíticas tienen
    gramática propia, así que conviene que las revise un hablante nativo.
  - Lo que falte cae al inglés.

## 2. Estructura en el repositorio (rama `julio/actividades`)

```
MAESTRO.md, data/harmonized/, harmonizacion/     datos y método (Antonio)
plataforma_local/
├── backend/                  API (Python 3.12, FastAPI, DuckDB)
│   ├── firecal/plan/         sources.py (contrato), events.py (CSV -> Parquet + controles), query.py (consultas)
│   ├── api/routers/plan.py   GET /api/...
│   ├── api/limits.py         protocolo de solicitudes (429/503, candados)
│   └── tests/                test_plan.py (casos de MAESTRO §12, margen), test_limits.py
├── frontend/                 interfaz React + Vite + MapLibre (base: rama dante)
│   ├── src/FireMapApp.jsx    mapa, paneles, calendario
│   ├── src/services/api.js   cliente de /api/*
│   └── dist/                 compilado (no se sube; lo genera `npm run build`)
├── Dockerfile (+ Dockerfile.dockerignore), docker-compose.yml   contexto = raíz del repo
└── docs/                     despliegue/falencias y beneficios NASA
```

---

## 3. Cómo ejecutarla

### Opción A: Docker (recomendada para mostrarla)

Requiere Docker Desktop abierto. Desde `plataforma_local/`:
```powershell
docker compose up --build          # ~2 min la primera vez; luego abre http://localhost:8000
```
Sin compose, desde la **raíz** del repositorio:
`docker build -f plataforma_local/Dockerfile -t firecal-cusco .` y `docker run --rm -p 8000:8000 firecal-cusco`.

La imagen compila la interfaz (Node), instala la API y **valida los CSV contra MAESTRO §6**: si los datos cambiaron,
la construcción falla. Pesa 1,33 GB y el contenedor usa ~130 MB de RAM.

### Opción B: desarrollo (Python + Node)

1. **API** (PowerShell, desde `plataforma_local/backend`):
   ```powershell
   py -3.12 -m venv .venv                                          # solo la primera vez
   .\.venv\Scripts\python -m pip install -r requirements-lock.txt  # solo la primera vez
   .\.venv\Scripts\python -m pip install -e . --no-deps            # solo la primera vez
   $env:PYTHONUTF8 = "1"
   .\.venv\Scripts\firecal plan-events     # ~2 s: valida los CSV y arma el Parquet
   .\.venv\Scripts\firecal serve           # API en http://localhost:8000 (docs en /docs)
   ```
2. **Interfaz** (otra terminal, desde `plataforma_local/frontend`; requiere Node 20 o superior):
   ```powershell
   npm install            # solo la primera vez
   npm run build          # compila a dist/; la API la sirve en http://localhost:8000
   npm run dev            # alternativa: modo desarrollo con recarga en http://localhost:5173
   ```
   En `npm run dev`, Vite reenvía `/api` al puerto 8000.
3. **Pruebas:** `ruff check .` y `pytest -q` en `backend/` (142 pruebas); `npx eslint .` en `frontend/`.

Opciones de la página: `?calendario=0` abre sin el calendario (útil para presentar el mapa).
Interfaz publicada en otro dominio (p. ej. Vercel): compilar con `VITE_API_BASE_URL=https://<api>` y, en la API,
`FIRECAL_CORS_ORIGINS=https://<dominio-de-la-interfaz>`.

Verificación de los datos (script de Antonio, funciona en Windows), desde la raíz del repo:
```powershell
python -I harmonizacion/verificar_datos.py data/harmonized/harmonizado_cusco_celda_dia.csv data/harmonized/focos_cusco_individuales.csv
```

---

## 4. Endpoints (contrato con la interfaz)

AOI: `departamento=PE-CUS` **o** `bbox=oeste,sur,este,norte` **o** `lat=..&lon=..&radio_km=..` (dentro de Cusco).

| Ruta | Parámetros | Devuelve |
| --- | --- | --- |
| `GET /api/departamentos` | — | Cusco (único con datos) y su límite |
| `GET /api/departamentos.geojson` | — | Solo el contorno de Cusco (FeatureCollection) |
| `GET /api/calendario` | AOI, `fecha_inicio`, `fecha_fin` (AAAA-MM, opcionales) | `matriz_focos_armonizados`, `matriz_anomalia`, `total_focos_armonizados`, `cortes_color`, `unidad`, `celdas[]` |
| `GET /api/anomalias` | AOI, `mes` | el mes con su margen, mediana e IQR, anomalía, `historial[]` y `dias[]` |
| `GET /api/focos.geojson` | AOI, `fecha_inicio`, `fecha_fin` | focos como puntos para el mapa (`eq_foco`, sensor, fecha, calidad; sin FRP); máx. 50 000 |
| `GET /api/hotspots.csv` | AOI, `fecha_inicio`, `fecha_fin` | CSV de focos (18 columnas del contrato); cabeceras `X-Row-Count` y `X-Total-Eq-Foco` |
| `GET /api/metadatos` | — | unidad, método (k, kT, margen), cobertura, sumas de control y créditos |
| `GET /health`, `GET /health/limits` | — | estado de los datos y del protocolo de solicitudes |

Celda del calendario:
```json
{"anio": 2001, "mes": 8, "sin_dato": false, "focos_armonizados": 176.02, "celdas_dia": 34,
 "focos_modis": 34, "focos_viirs": 0, "mediana_hist": 151.5, "anomalia": 0.21, "categoria": "incierta",
 "calidad": "extrapolado", "fraccion_extrapolada": 1.0, "incertidumbre": 77.4, "rango": [98.6, 253.4],
 "anomalia_rango": [-0.45, 0.87], "fuente_serie": "Terra*kT", "parcial": false}
```

Errores: **404 "Sin datos"**; **422** con el motivo (AOI vacío, rango invertido, fecha mal escrita, área demasiado
grande, demasiados focos para el mapa); **429/503** del protocolo de solicitudes, con `Retry-After`.
El backend sintético anterior (`/api/v1`) está desactivado (`api.legacy_v1: false`).

---

## 5. Casos de prueba de MAESTRO §12 (todos pasan)

| Consulta | Esperado | Obtenido |
| --- | --- | --- |
| Todo el periodo | 15 732 (36 260 celdas-día; 58 779 focos en la descarga) | 15 732,03 · 36 260 · 58 779 |
| 2005 / 2012 / 2013 / 2020 / 2025 | 1355 / 678 / 424 / 1206 / 385 | iguales (±1) |
| Antes de 2000-11-04, o fuera de Cusco | "sin datos" (no cero) | 404 "Sin datos" |
| Σ `eq_foco` de la descarga | = total en pantalla | igual para departamento, rectángulo y punto |
| Margen de agosto de 2001 (ejemplo de Antonio) | 176,02 · rango 98,6–253,4 · "incierta" | igual |

---

## 6. ¿Servidor local u otra opción?

| Opción | Para qué sirve | Ventajas | Límites |
| --- | --- | --- | --- |
| **Servidor local** (`firecal serve` en tu PC) | Desarrollar y probar | Inmediato, sin costo | Solo tú (o tu red local) lo ves; si apagas la PC o el sistema se queda sin memoria, se cae (ya pasó una vez) |
| **Docker local** (`docker compose up`) | Ensayar exactamente lo que irá a la nube | Mismo resultado en cualquier máquina | Sigue siendo local |
| **Google Cloud Run** (proyecto `sonic-mile-514718-r5` ya listo) | **Mostrar al jurado** con una URL pública y HTTPS | Usa este mismo Dockerfile; escala solo; los créditos de la prueba lo cubren | Hay que vigilar el presupuesto; con 0 instancias mínimas la primera visita tarda unos segundos |
| Interfaz en Vercel + API en Cloud Run | Si Dante quiere mantener Vercel | Interfaz en CDN | Dos despliegues, CORS y `VITE_API_BASE_URL` |

**Recomendación:** servidor local o Docker para trabajar, y **una sola imagen en Cloud Run** para la evaluación, con
1 instancia mínima durante el concurso y 0 después. El comando y el procedimiento están en
[`docs/DESPLIEGUE_Y_FALENCIAS.md`](docs/DESPLIEGUE_Y_FALENCIAS.md); no se ha desplegado aún.

---

## 7. Procedimiento seguido (registro)

1. Clonar el backend de pruebas (`project_nasa`, rama `backend`) y adaptarlo al PLAN: endpoints GET, Docker y
   protocolo de solicitudes.
2. Integrar `antonio/modelo` y corregir `verificar_datos.py` para Windows (MAESTRO §7 y §11).
3. Reemplazar los datos sintéticos por los CSV de Antonio, validados contra MAESTRO §6; solo Cusco; sin FRP.
4. De `antonio/backend-modelo`:
   - calidad del mes desde los datos;
   - `FIRECAL_CORS_ORIGINS` y `/api/departamentos.geojson`;
   - **margen de los meses extrapolados** y categoría "incierta";
   - **Dockerfile con contexto en la raíz del repo**.
5. Nombre de campo **`focos_armonizados`** en la API (decisión del equipo).
6. Interfaz de Dante (rama `dante`) adaptada:
   - **Se mantuvo:** el diseño, MapLibre, los paneles, la selección de área con vista satelital y la barra temporal.
   - **Se quitó:** los datos demo, la función FIRMS en vivo de Vercel, los otros departamentos, el FRP y el
     "riesgo" calculado con FRP.
   - **Se agregó:** el calendario mes × año, el margen de los extrapolados, la descarga del contrato y la conexión
     a `/api/*`.

## 8. Pendientes

- [ ] Desplegar en Cloud Run cuando el equipo lo decida.
- [ ] Analíticas descargables de MAESTRO P4 (serie anual por fuente, perfil estacional, bandas de altitud). El mapa
      ya conserva su dibujo para poder exportarlo como imagen.
- [ ] Reducir el paquete JS de la interfaz (1,26 MB, casi todo MapLibre) con carga diferida, si hace falta.
- [ ] `harmonizacion/sequia_fuego/n_efectivo_potencia.py` tiene el mismo problema de Windows (`≈`).
