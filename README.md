# Firewatch Perú — Geo App

Base frontend para el calendario armonizado de incendios forestales del equipo NASA Space Apps 2026.

## Stack

- React + Vite
- MapLibre GL JS (WebGL)
- Mapa vectorial OpenFreeMap / OpenStreetMap
- JavaScript
- CSS responsive sin framework visual
- Adaptador preparado para FastAPI

## Desarrollo local

```bash
npm install
npm run dev
```

La aplicación funciona con datos sintéticos cuando `VITE_API_BASE_URL` no está configurado.

Para conectarla con el backend:

```bash
cp .env.example .env
npm run dev
```

Endpoints esperados:

- `GET /api/calendario`
- `GET /api/anomalias`
- `GET /api/hotspots.csv`
- `GET /api/metadatos`

## Alcance de esta base

- Zona de estudio exclusiva para el departamento de Cusco
- Límite departamental oficial del INEI, distribuido por el IGN
- Resaltado interactivo por hover y selección por clic o toque
- Máscara territorial, mapa de calor WebGL y detecciones puntuales
- Selección rectangular con análisis agregado, resaltado de focos y descarga CSV
- Filtrado geográfico punto-en-polígono para excluir detecciones fuera de Cusco
- Métricas de eventos, FRP y confianza
- Descarga CSV
- Diseño responsive
- Modo demo y modo API
- Interfaz cartográfica de pantalla completa enfocada únicamente en Cusco
- Capas de calor, detecciones puntuales y límite del área de interés
- Cronología interactiva de los últimos cinco días

## Datos FIRMS en Vercel

La función `api/fire-overview.js` consulta detecciones recientes de MODIS y VIIRS, filtra confianza menor a 70 % y deduplica por fecha y celda aproximada de 1 km.

Configura la variable secreta `FIRMS_MAP_KEY` en Vercel. La clave nunca debe usar el prefijo `VITE_`, porque eso la expondría al navegador.

> We acknowledge the use of data and/or imagery from NASA's FIRMS.
