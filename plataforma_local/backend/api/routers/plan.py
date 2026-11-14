"""Endpoints del plan de trabajo (PLAN.md sección 4, contrato Julio <-> Dante).

- ``GET /api/calendario``   AOI + rango -> matriz mes x año (conteos y anomalía normalizada).
- ``GET /api/anomalias``    mes consultado frente a la mediana histórica de su era de sensores.
- ``GET /api/hotspots.csv`` descarga de eventos armonizados del rango (CSV UTF-8 con BOM).
- ``GET /api/metadatos``    versión, umbral de confianza, reglas y advertencias.
- ``GET /api/departamentos`` departamentos disponibles (código ISO, nombre, área).

AOI: ``departamento`` (p. ej. PE-CUS), ``bbox=oeste,sur,este,norte`` o
``lat`` + ``lon`` + ``radio_km``.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from firecal.plan.events import PLAN_VERSION, VIIRS_CONF_NORM
from firecal.plan.query import (
    CATEGORY_EDGES,
    CSV_COLUMNS,
    MIN_YEARS,
    PlanError,
    PlanNoData,
    PlanNotReady,
    PlanStore,
)

router = APIRouter(prefix="/api", tags=["plan (MVP)"])

FIRMS_CREDIT = ("We acknowledge the use of data and/or imagery from NASA's FIRMS "
                "(https://earthdata.nasa.gov/firms).")
NOTE_SYNTHETIC = "Datos sintéticos (simulados con el formato de FIRMS): no usar para decisiones."

Dep = Annotated[str | None, Query(description="Código ISO del departamento, p. ej. PE-CUS")]
BBox = Annotated[str | None, Query(description="oeste,sur,este,norte en grados WGS84")]
Lat = Annotated[float | None, Query(description="Latitud del centro (con lon y radio_km)")]
Lon = Annotated[float | None, Query(description="Longitud del centro")]
Radio = Annotated[float | None, Query(description="Radio en km")]
Inicio = Annotated[str | None, Query(description="AAAA-MM (por defecto, inicio de la serie)")]
Fin = Annotated[str | None, Query(description="AAAA-MM (por defecto, último mes)")]


def _store(request: Request) -> PlanStore:
    store: PlanStore = request.app.state.plan
    try:
        store.meta  # noqa: B018 - fuerza la carga y valida que existan los datos
    except PlanNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return store


def _envelope(store: PlanStore, body: dict) -> dict:
    meta = store.meta
    notes = ([NOTE_SYNTHETIC] if meta["data_mode"] == "synthetic" else []) + body.pop("notes", [])
    return {"data_mode": meta["data_mode"], "version": meta["plan_version"],
            "generado": datetime.now(UTC).isoformat(timespec="seconds"), **body, "notes": notes}


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
    """Departamentos con eventos procesados (para el selector del frontend)."""
    store = _store(request)
    deps = [{"code": d["code"], "name": d["name"], "area_km2": round(d["area_km2"], 1)}
            for d in sorted(store.departments.values(), key=lambda d: d["name"])]
    return _envelope(store, {"departamentos": deps})


@router.get("/calendario")
def calendario(request: Request, departamento: Dep = None, bbox: BBox = None, lat: Lat = None,
               lon: Lon = None, radio_km: Radio = None, fecha_inicio: Inicio = None,
               fecha_fin: Fin = None) -> dict:
    """Matriz mes x año de eventos armonizados y su anomalía normalizada (A + C)."""
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
    """Un mes frente a la mediana histórica del mismo mes en su era de sensores."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    if _custom_aoi(bbox, lat):
        with request.app.state.gate.turn():
            return _envelope(store, _call(store.anomaly, aoi, mes))
    return _envelope(store, _call(store.anomaly, aoi, mes))


@router.get("/hotspots.csv", response_class=StreamingResponse)
def hotspots_csv(request: Request, fecha_inicio: Annotated[str, Query(description="AAAA-MM")],
                 fecha_fin: Annotated[str, Query(description="AAAA-MM")],
                 departamento: Dep = None, bbox: BBox = None, lat: Lat = None, lon: Lon = None,
                 radio_km: Radio = None) -> StreamingResponse:
    """Eventos armonizados del rango en CSV (UTF-8 con BOM: abre bien en Excel)."""
    store = _store(request)
    aoi = _call(store.resolve_aoi, departamento, bbox, lat, lon, radio_km)
    # El turno se toma aquí y se libera cuando termina de enviarse el CSV (o si el cliente corta).
    gate = request.app.state.gate
    gate.acquire()
    try:
        sql, params = _call(store.hotspots_query, aoi, fecha_inicio, fecha_fin)
        chunk = store.settings.params.api.csv_chunk_rows
        cur = store.cursor()
        cur.execute(sql, params)
    except BaseException:
        gate.release()
        raise

    def rows() -> Iterator[bytes]:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(CSV_COLUMNS)
        yield ("﻿" + buf.getvalue()).encode("utf-8")
        try:
            while batch := cur.fetchmany(chunk):
                buf.seek(0)
                buf.truncate()
                w.writerows(batch)
                yield buf.getvalue().encode("utf-8")
        finally:
            cur.close()
            gate.release()

    tag = (departamento or aoi.kind).lower()
    name = f"focos_{tag}_{fecha_inicio}_{fecha_fin}.csv"
    return StreamingResponse(rows(), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{name}"',
        "X-Data-Mode": store.meta["data_mode"]})


@router.get("/metadatos")
def metadatos(request: Request) -> dict:
    """Versión del armonizador, umbral de confianza, reglas y advertencias."""
    store = _store(request)
    m = store.meta
    return _envelope(store, {
        "armonizador": {
            "version": PLAN_VERSION,
            "alternativas": ["A: grilla común de ~1 km (0.01°)",
                             "C: anomalías normalizadas por era"],
            "deduplicacion": "Misma celda de 1 km y mismo día local (America/Lima): un evento; se "
                             "conserva la detección de mayor FRP (MW).",
            "eras": {"MODIS": "ene-2003 a ene-2012 (Terra + Aqua)",
                     "MODIS+VIIRS": "desde feb-2012 (Terra + Aqua + un solo VIIRS)"},
            "constelacion": "Un VIIRS a la vez para no inflar conteos al sumar satélites: "
                            + ", ".join(f"{s} desde {a}" for s, a, _ in m["viirs_cadena"]),
            "anomalia": "(n_eventos - mediana del mismo mes en la misma era) / max(IQR, 1)",
            "min_anios_para_anomalia": MIN_YEARS,
            "categorias": [{"hasta": e if e != float("inf") else None, "nombre": n}
                           for e, n in CATEGORY_EDGES],
            "alternativa_B": "Calibración por solapamiento disponible en /api/v1/calendar "
                             "(backend anterior, focos equivalentes a MODIS-Aqua diurno).",
        },
        "umbral_confianza": {"minimo": m["umbral_confianza"],
                             "viirs_conf_norm": VIIRS_CONF_NORM,
                             "modis_conf_norm": "confidence / 100"},
        "cobertura": {"primer_mes": m["primer_mes"], "ultima_fecha": m["ultimo_fecha_local"],
                      "departamentos": m["departamentos"]},
        "conteos": {"detecciones_limpias": m["n_detecciones_limpias"],
                    "detecciones_constelacion": m["n_detecciones_constelacion"],
                    "eventos": m["n_eventos"], "fusionadas": m["fusionadas"],
                    "eventos_multisensor": m["eventos_multisensor"]},
        "creditos": FIRMS_CREDIT,
        "notes": ["Se miden focos de calor detectables por satélite, no número de incendios.",
                  "VIIRS (375 m) detecta fuegos más pequeños que MODIS (1 km): por eso la "
                  "anomalía se calcula dentro de cada era.",
                  "Limitación: la deriva orbital de Terra y Aqua (desde ~2020-2022) cambia su hora "
                  "de paso; A + C no la corrige. La alternativa B (/api/v1) sí la modela."],
    })
