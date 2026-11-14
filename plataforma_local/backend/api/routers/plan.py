"""Endpoints del plan de trabajo (PLAN.md §4, contrato Julio <-> Dante) sobre los datos de Cusco.

- ``GET /api/departamentos``  región disponible (solo Cusco) con su límite en GeoJSON.
- ``GET /api/departamentos.geojson`` solo el contorno (FeatureCollection) para el mapa.
- ``GET /api/calendario``     AOI + rango -> matriz mes x año de focos armonizados y anomalía.
- ``GET /api/anomalias``      un mes frente a la mediana del mismo mes + detalle diario.
- ``GET /api/hotspots.csv``   focos del rango con las 18 columnas del contrato (CSV UTF-8 con BOM).
- ``GET /api/focos.geojson``   focos del rango como puntos para el mapa (peso = eq_foco, sin FRP).
- ``GET /api/metadatos``      método, factores, calidad, cobertura, sumas de control y créditos.
- ``GET /api/resumen`` y ``GET /api/analitica/*``  analíticas sencillas, cada una con una frase
  en lenguaje simple (firecal/plan/analitica.py).

AOI: ``departamento=PE-CUS`` o ``bbox=oeste,sur,este,norte`` o ``lat`` + ``lon`` + ``radio_km``.
Unidad: **focos armonizados**; en la API el campo se llama ``focos_armonizados`` (decisión del
equipo). La descarga CSV conserva las 18 columnas del contrato de focos (``eq_foco``).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from firecal.plan.events import PLAN_VERSION
from firecal.plan.query import (
    CATEGORY_EDGES,
    MIN_YEARS,
    NOTE_2025,
    NOTE_EXTRAPOLADO,
    UNIDAD,
    PlanError,
    PlanNoData,
    PlanNotReady,
    PlanStore,
)
from firecal.plan.sources import COLS_FOCOS

router = APIRouter(prefix="/api", tags=["plan (MVP)"])

FIRMS_CREDIT = ("We acknowledge the use of data and/or imagery from NASA's FIRMS "
                "(https://earthdata.nasa.gov/firms).")

Dep = Annotated[str | None, Query(description="Código del departamento: PE-CUS (único con datos)")]
BBox = Annotated[str | None, Query(description="oeste,sur,este,norte en grados WGS84")]
Lat = Annotated[float | None, Query(description="Latitud del centro (con lon y radio_km)")]
Lon = Annotated[float | None, Query(description="Longitud del centro")]
Radio = Annotated[float | None, Query(description="Radio en km")]
Inicio = Annotated[str | None, Query(description="AAAA-MM (por defecto 2000-11)")]
Fin = Annotated[str | None, Query(description="AAAA-MM (por defecto 2025-12)")]


def _store(request: Request) -> PlanStore:
    store: PlanStore = request.app.state.plan
    try:
        store.meta  # noqa: B018 - fuerza la carga y valida que existan los datos
    except PlanNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return store


def _envelope(store: PlanStore, body: dict) -> dict:
    meta = store.meta
    return {"data_mode": meta["data_mode"], "version": meta["plan_version"],
            "generado": datetime.now(UTC).isoformat(timespec="seconds"), **body,
            "notes": body.pop("notes", [])}


def _custom_aoi(bbox, lat) -> bool:
    """AOI dibujado (bbox o punto): no está en caché y cuesta más -> pide turno en HeavyGate."""
    return bool(bbox) or lat is not None


def _call(fn, *args):
    try:
        return fn(*args)
    except PlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PlanNoData as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/departamentos")
def departamentos(request: Request) -> dict:
    """Región con datos armonizados y validados (solo Cusco) y su límite (FAO GAUL) en GeoJSON."""
    store = _store(request)
    reg = store.meta["region"]
    return _envelope(store, {
        "departamentos": [{"code": reg["code"], "name": reg["name"], "datos": "armonizados"}],
        "geojson": store.region_geojson,
        "notes": ["Prototipo centrado en Cusco: es la única región con factores de armonización "
                  "validados. Otras regiones responden 'sin datos'."]})


@router.get("/departamentos.geojson")
def departamentos_geojson(request: Request) -> dict:
    """Solo el contorno de Cusco (FeatureCollection), para cargarlo directo en el mapa.

    Misma ruta que documentó antonio/backend-modelo (docs/DESPLIEGUE_MODELO.md) para Dante."""
    store = _store(request)
    return {**store.region_geojson, "data_mode": store.meta["data_mode"]}


@router.get("/calendario")
def calendario(request: Request, departamento: Dep = None, bbox: BBox = None, lat: Lat = None,
               lon: Lon = None, radio_km: Radio = None, fecha_inicio: Inicio = None,
               fecha_fin: Fin = None) -> dict:
    """Matriz mes x año de focos armonizados, anomalía (con margen) y cortes de color."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    if _custom_aoi(bbox, lat):
        with request.app.state.gate.turn():
            return _envelope(store, _call(store.calendar, aoi, fecha_inicio, fecha_fin))
    return _envelope(store, _call(store.calendar, aoi, fecha_inicio, fecha_fin))


@router.get("/anomalias")
def anomalias(request: Request, mes: Annotated[str, Query(description="AAAA-MM")],
              departamento: Dep = None, bbox: BBox = None, lat: Lat = None, lon: Lon = None,
              radio_km: Radio = None) -> dict:
    """Un mes frente a la mediana histórica del mismo mes, con su detalle diario."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    if _custom_aoi(bbox, lat):
        with request.app.state.gate.turn():
            return _envelope(store, _call(store.anomaly, aoi, mes))
    return _envelope(store, _call(store.anomaly, aoi, mes))


@router.get("/focos.geojson")
def focos_geojson(request: Request, fecha_inicio: Annotated[str, Query(description="AAAA-MM")],
                  fecha_fin: Annotated[str, Query(description="AAAA-MM")],
                  departamento: Dep = None, bbox: BBox = None, lat: Lat = None, lon: Lon = None,
                  radio_km: Radio = None) -> dict:
    """Focos del rango como puntos GeoJSON (mapa de calor y puntos). Peso = ``eq_foco``.

    Máximo ``api.max_geojson_features`` focos por consulta; para más, usar la descarga CSV."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    if _custom_aoi(bbox, lat):
        with request.app.state.gate.turn():
            return _envelope(store, _call(store.focos_geojson, aoi, fecha_inicio, fecha_fin))
    return _envelope(store, _call(store.focos_geojson, aoi, fecha_inicio, fecha_fin))


@router.get("/hotspots.csv", response_class=StreamingResponse)
def hotspots_csv(request: Request, fecha_inicio: Annotated[str, Query(description="AAAA-MM")],
                 fecha_fin: Annotated[str, Query(description="AAAA-MM")],
                 departamento: Dep = None, bbox: BBox = None, lat: Lat = None, lon: Lon = None,
                 radio_km: Radio = None) -> StreamingResponse:
    """Focos del rango con las 18 columnas del contrato (UTF-8 con BOM: abre bien en Excel).

    La cabecera ``X-Total-Eq-Foco`` trae Σ eq_foco de las filas: es el total que muestra la web."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    # El turno se toma aquí y se libera cuando termina de enviarse el CSV (o si el cliente corta).
    gate = request.app.state.gate
    gate.acquire()
    try:
        sql, params, n_rows, total = _call(store.hotspots_query, aoi, fecha_inicio, fecha_fin)
        chunk = store.settings.params.api.csv_chunk_rows
        cur = store.cursor()
        cur.execute(sql, params)
    except BaseException:
        gate.release()
        raise

    def rows() -> Iterator[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(COLS_FOCOS)
        yield ("﻿" + buf.getvalue()).encode("utf-8")
        try:
            while batch := cur.fetchmany(chunk):
                buf.seek(0)
                buf.truncate()
                w.writerows(["" if v is None else v for v in row] for row in batch)
                yield buf.getvalue().encode("utf-8")
        finally:
            cur.close()
            gate.release()

    tag = "cusco" if aoi.whole_region else aoi.kind
    name = f"focos_{tag}_{fecha_inicio}_{fecha_fin}.csv"
    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Data-Mode": store.meta["data_mode"], "X-Row-Count": str(n_rows),
        "X-Total-Eq-Foco": f"{total:.2f}"})


def _analitica(request: Request, nombre: str, departamento, bbox, lat, lon, radio_km,
               **extra) -> dict:
    """Analíticas sencillas (firecal/plan/analitica.py): una pregunta, una frase y sus datos."""
    from firecal.plan import analitica

    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    fn = getattr(analitica, nombre)
    if _custom_aoi(bbox, lat):
        with request.app.state.gate.turn():
            return _envelope(store, _call(lambda: fn(store, aoi, **extra)))
    return _envelope(store, _call(lambda: fn(store, aoi, **extra)))


@router.get("/resumen")
def resumen(request: Request, departamento: Dep = None, bbox: BBox = None, lat: Lat = None,
            lon: Lon = None, radio_km: Radio = None) -> dict:
    """Cinco frases en lenguaje sencillo sobre el fuego del AOI."""
    return _analitica(request, "resumen", departamento, bbox, lat, lon, radio_km)


@router.get("/analitica/estacionalidad")
def analitica_estacionalidad(request: Request, departamento: Dep = None, bbox: BBox = None,
                             lat: Lat = None, lon: Lon = None, radio_km: Radio = None) -> dict:
    """En qué meses se concentra el fuego (mediana y rango por mes, temporada y mes pico)."""
    return _analitica(request, "estacionalidad", departamento, bbox, lat, lon, radio_km)


@router.get("/analitica/ranking")
def analitica_ranking(request: Request, departamento: Dep = None, bbox: BBox = None,
                      lat: Lat = None, lon: Lon = None, radio_km: Radio = None) -> dict:
    """Años ordenados del más al menos activo, frente a un año típico."""
    return _analitica(request, "ranking", departamento, bbox, lat, lon, radio_km)


@router.get("/analitica/acumulado")
def analitica_acumulado(request: Request,
                        anio: Annotated[int | None, Query(description="Año (por defecto, el "
                                                          "último completo)")] = None,
                        departamento: Dep = None, bbox: BBox = None, lat: Lat = None,
                        lon: Lon = None, radio_km: Radio = None) -> dict:
    """Curva acumulada de un año frente a la banda histórica."""
    return _analitica(request, "acumulado", departamento, bbox, lat, lon, radio_km, anio=anio)


@router.get("/analitica/altitud")
def analitica_altitud(request: Request, departamento: Dep = None, bbox: BBox = None,
                      lat: Lat = None, lon: Lon = None, radio_km: Radio = None) -> dict:
    """Reparto del fuego por franja de altitud."""
    return _analitica(request, "altitud", departamento, bbox, lat, lon, radio_km)


@router.get("/analitica/recurrencia")
def analitica_recurrencia(request: Request,
                          limite: Annotated[int, Query(ge=0, le=20000, description="Celdas a "
                                                       "devolver, de la más repetida a la "
                                                       "menos")] = 5000,
                          departamento: Dep = None, bbox: BBox = None, lat: Lat = None,
                          lon: Lon = None, radio_km: Radio = None) -> dict:
    """En cuántos años distintos ardió cada celda de ~1 km (desde 2013)."""
    return _analitica(request, "recurrencia", departamento, bbox, lat, lon, radio_km,
                      limite=limite)


@router.get("/metadatos")
def metadatos(request: Request) -> dict:
    """Método, factores, calidad, cobertura, sumas de control y créditos (MAESTRO.md v1.2)."""
    store = _store(request)
    m = store.meta
    f = m["factores"]
    return _envelope(store, {
        "unidad": {**UNIDAD,
                   "campos": "focos_armonizados en la API = suma de eq_hotspots (celda-día) o "
                             "eq_foco (foco); nunca contar filas ni sumar n_modis + n_viirs"},
        "armonizacion": {
            "version_datos": PLAN_VERSION,
            "grilla": "celda de 0.01° (~1.1 km) × día local (UTC−5); presencia de fuego",
            "serie": [
                {"periodo": "2000-11-04 a 2002-07-03", "fuente_serie": "Terra*kT",
                 "calidad": "extrapolado", "kT": {"alto": f.get("Terra*kT|alto"),
                                                  "bajo": f.get("Terra*kT|bajo")}},
                {"periodo": "2002-07-04 a 2012-12-31", "fuente_serie": "MODIS",
                 "calidad": "referencia", "peso": 1.0},
                {"periodo": "desde 2013-01-01", "fuente_serie": "VIIRS*k", "calidad": "calibrado",
                 "k": {"alto": f.get("VIIRS*k|alto"), "bajo": f.get("VIIRS*k|bajo")}},
            ],
            "estratos": "alto ≥ 2500 m, bajo < 2500 m (altitud SRTM)",
            "validacion": "k calibrado en 2013-2019; en 2020-2024 VIIRS×k / MODIS real = "
                          "0.90-1.09 por año",
            "filtros": "type = 0 (vegetación); MODIS confidence ≥ 30; VIIRS n o h; solo S-NPP",
            "anomalia": "(valor − mediana del mismo mes) / max(IQR, 1), con los meses completos "
                        "de calidad referencia o calibrado",
            "min_anios_para_anomalia": MIN_YEARS,
            "categorias": [{"hasta": e if e != float("inf") else None, "nombre": n}
                           for e, n in CATEGORY_EDGES],
        },
        "cobertura": {"region": m["region"], "desde": m["cobertura_desde"],
                      "hasta": m["cobertura_hasta"], "ultimo_dia_con_focos": m["ultimo_dia"],
                      "nota": "Serie histórica: no incluye 2026."},
        "controles_maestro": {k: {"filas": v["filas"], "suma": v["suma"],
                                  "coincide": v["coincide_maestro"]}
                              for k, v in m["controles"].items()},
        "creditos": [FIRMS_CREDIT, "Límite de Cusco: FAO GAUL 2015 (nivel 1, simplificado).",
                     "Altitud: SRTM.", "Mapa base: © OpenStreetMap."],
        "notes": ["Un foco es un píxel con anomalía térmica, no un incendio ni un área quemada.",
                  "No se calcula área quemada y el FRP no se usa (no está armonizado entre "
                  "sensores).",
                  NOTE_EXTRAPOLADO, NOTE_2025,
                  "Cobertura validada: solo Cusco. Los factores k y kT no se reutilizan en otras "
                  "regiones."],
    })
