# Firewatch Perú — Geo App

Base frontend para el calendario armonizado de incendios forestales del equipo NASA Space Apps 2026.

## Stack

- React + Vite
- Leaflet + React Leaflet
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

- Selección de departamento y periodo
- Mapa Leaflet con AOI y hotspots de muestra
- Métricas de eventos, anomalía, FRP y confianza
- Calendario histórico mes × año
- Descarga CSV
- Diseño responsive
- Modo demo y modo API

> We acknowledge the use of data and/or imagery from NASA's FIRMS.
