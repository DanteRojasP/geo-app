"""Servicios de focos (CSV/GeoJSON), mapa de celdas, regiones, metadatos y perspectiva."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import date, timedelta

import h3
import pandas as pd
import shapely
from shapely.geometry import mapping

from api.db import Repository
from api.services.common import (
    NOTE_DIURNAL,
    NOTE_H3,
    NOTE_PROVISIONAL,
    UNIT_HARMONIZED,
    AOIError,
    ResolvedAOI,
    clean_number,
    envelope,
)
from firecal.etl.firms_schema import is_nrt_version

CSV_COLUMNS = ["id", "sensor", "satellite", "acq_utc", "local_date", "lat", "lon",
               "confidence_cat", "confidence_raw", "frp", "daynight", "type", "version", "h3_7"]
DAYS_PER_YEAR = 365.25


# --------------------------------------------------------------------------------------
# /hotspots
# --------------------------------------------------------------------------------------
def hotspots_in_aoi(repo: Repository, aoi: ResolvedAOI, start: date, end: date) -> pd.DataFrame:
    """Focos limpios dentro del AOI (filtro exacto punto-en-polígono) entre dos fechas locales."""
    max_years = repo.settings.params.api.max_csv_years
    if end < start:
        raise AOIError("La fecha 'end' debe ser posterior o igual a 'start'.")
    if (end - start) > timedelta(days=DAYS_PER_YEAR * max_years):
        raise AOIError(f"El rango de fechas supera el máximo de {max_years} años para la "
                       "descarga de focos.")
    df = repo.hotspots(aoi.geometry.bounds, start, end)
    if df.empty:
        return df
    geom = aoi.geometry
    shapely.prepare(geom)
    inside = shapely.contains_xy(geom, df["lon"].to_numpy(), df["lat"].to_numpy())
    return df[inside].reset_index(drop=True)


def csv_stream(df: pd.DataFrame, data_mode: str, chunk_rows: int) -> Iterator[bytes]:
    """CSV en utf-8-sig (BOM para Excel en Windows), por bloques."""
    out = df.copy()
    out["acq_utc"] = pd.to_datetime(out["acq_utc"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out["local_date"] = pd.to_datetime(out["local_date"]).dt.strftime("%Y-%m-%d")
    out["data_mode"] = data_mode
    cols = [*CSV_COLUMNS, "data_mode"]
    yield "﻿".encode()
    for i in range(0, max(len(out), 1), chunk_rows):
        buf = io.StringIO()
        out.iloc[i:i + chunk_rows][cols].to_csv(buf, index=False, header=(i == 0),
                                                lineterminator="\r\n")
        yield buf.getvalue().encode("utf-8")


def hotspots_geojson(repo: Repository, df: pd.DataFrame, aoi: ResolvedAOI) -> dict:
    limit = repo.settings.params.api.max_geojson_features
    if len(df) > limit:
        raise AOIError(f"La consulta devuelve {len(df):,} focos; el máximo en GeoJSON es "
                       f"{limit:,}. Usa format='csv' o un rango menor.")
    feats = []
    for r in df.itertuples():
        feats.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
            "properties": {
                "id": int(r.id), "sensor": r.sensor, "satellite": r.satellite,
                "acq_utc": pd.Timestamp(r.acq_utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "local_date": pd.Timestamp(r.local_date).strftime("%Y-%m-%d"),
                "confidence_cat": r.confidence_cat, "frp": clean_number(r.frp),
                "daynight": r.daynight, "version": r.version, "h3_7": r.h3_7,
            },
        })
    notes: list[str] = []
    if len(df) and df["version"].map(is_nrt_version).any():
        notes.append(NOTE_PROVISIONAL)
    return {"type": "FeatureCollection", **envelope(repo, notes), "aoi": aoi.info(),
            "n_features": len(feats), "features": feats}


# --------------------------------------------------------------------------------------
# /map/cells
# --------------------------------------------------------------------------------------
def map_cells(repo: Repository, aoi: ResolvedAOI, year: int, month: int) -> dict:
    """GeoJSON de hexágonos H3 del AOI con valor armonizado > 0 en el mes."""
    plan = repo.data.months
    row = plan[(plan["year"] == year) & (plan["month"] == month)]
    if row.empty:
        raise AOIError(f"No hay datos armonizados para {year}-{month:02d}.")
    info = row.iloc[0]
    vals = repo.cell_month_values(aoi.cells, year, month)
    feats = []
    for r in vals.itertuples():
        ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(r.h3)]
        ring.append(ring[0])
        feats.append({
            "type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"h3": r.h3, "value": clean_number(r.value),
                           "p10": clean_number(r.p10), "p90": clean_number(r.p90),
                           "raw_value": clean_number(r.raw_value)},
        })
    notes = [NOTE_H3, NOTE_DIURNAL,
             "Solo se incluyen celdas con valor > 0; las demás valen 0.",
             "p10/p90 por celda = incertidumbre del factor de conversión (no del mes)."]
    if bool(info["is_provisional"]):
        notes.append(NOTE_PROVISIONAL)
    return {"type": "FeatureCollection", **envelope(repo, notes), "unit": UNIT_HARMONIZED,
            "year": year, "month": month, "source": info["source"],
            "satellite": info["satellite"], "provisional": bool(info["is_provisional"]),
            "aoi": aoi.info(), "n_cells_with_data": len(feats), "features": feats}


# --------------------------------------------------------------------------------------
# /regions
# --------------------------------------------------------------------------------------
def regions_geojson(repo: Repository) -> dict:
    tol = repo.settings.params.api.region_simplify_deg
    feats = []
    for r in repo.regions.values():
        geom = r.geometry.simplify(tol, preserve_topology=True) if tol else r.geometry
        feats.append({"type": "Feature", "geometry": mapping(geom),
                      "properties": {"code": r.code, "name": r.name, "level": r.level,
                                     "area_km2": round(r.area_km2, 1),
                                     "n_cells": int(len(repo.region_cells[r.code]))}})
    return {"type": "FeatureCollection", **envelope(repo, []), "features": feats}


# --------------------------------------------------------------------------------------
# /forecast
# --------------------------------------------------------------------------------------
NOTE_FORECAST_PENDING = ("Perspectiva no disponible: el modelo predictivo aún no está entrenado "
                         "(Fase 7).")
NOTE_NO_SKILL = "El modelo no supera a la climatología; mostrar como referencia."
NOTE_SYNTHETIC_SKILL = "Datos sintéticos: el skill del modelo no es interpretable."


def forecast(repo: Repository, region_code: str) -> dict:
    if region_code not in repo.regions:
        raise AOIError(f"Región desconocida '{region_code}'. Disponibles: {sorted(repo.regions)}")
    meta = repo.forecast_metadata()
    if meta is None or region_code not in meta.get("forecasts", {}):
        return {**envelope(repo, [NOTE_FORECAST_PENDING]), "region_code": region_code,
                "available": False}
    f = meta["forecasts"][region_code]
    notes = []
    if not meta.get("beats_climatology", False):
        notes.append(NOTE_NO_SKILL)
    if repo.data_mode == "synthetic":
        notes.append(NOTE_SYNTHETIC_SKILL)
    return {**envelope(repo, notes), "region_code": region_code, "available": True,
            "target_year": f.get("target_year"), "target_month": f.get("target_month"),
            "prob_above_median": f.get("prob_above_median"),
            "expected_value": f.get("expected_value"), "skill": meta.get("skill"),
            "beats_climatology": meta.get("beats_climatology"),
            "model_version": meta.get("model_version")}


# --------------------------------------------------------------------------------------
# /meta
# --------------------------------------------------------------------------------------
BAND_DESCRIPTION = (
    "band_p10/band_p90: intervalo 10-90 % del valor armonizado del AOI. Combina (1) la "
    "incertidumbre del factor de conversión VIIRS->Aqua (bootstrap por bloques de años, sumado "
    "sobre los estratos del AOI) y (2) el error observado de la conversión, que depende del "
    "conteo predicho del AOI completo (estimado por leave-one-year-out sin los años reservados). "
    "En meses observados por Aqua (modis_observed) no hay banda (band = valor)."
)


def meta(repo: Repository) -> dict:
    p = repo.settings.params
    hp = p.harmonization
    metrics = repo.validation_metrics() or {}
    chains = metrics.get("chains", {})
    params = repo.params
    regional = params[params["level"].isin(["region", "region*region"])]
    plan = repo.data.months
    return {
        **envelope(repo, [NOTE_DIURNAL]),
        "unit": UNIT_HARMONIZED,
        "unit_description": (
            "Focos de calor equivalentes a los que detectaría MODIS-Aqua en sus pasadas DIURNAS. "
            "Las detecciones nocturnas no entran al calendario armonizado. Mide actividad de "
            "quema detectable por satélite, no número de incendios."),
        "band_description": BAND_DESCRIPTION,
        "last_update": repo.last_update,
        "db_modified": repo.db_modified,
        "series": {"first": f"{int(plan.iloc[0].year)}-{int(plan.iloc[0].month):02d}",
                   "last": f"{int(plan.iloc[-1].year)}-{int(plan.iloc[-1].month):02d}",
                   "series_start": hp.series_start,
                   "aqua_observed_until": hp.aqua_observed_until,
                   "months_by_source": plan.groupby("source").size().to_dict()},
        "climatology_base_years": list(p.climatology.base_years),
        "satellite_coverage": repo.coverage.to_dict(orient="records"),
        "harmonization": {
            "method": "razón de sumas por estrato (celda padre H3 res 4 x temporada; fusión a "
                      "res 3 y regional), bootstrap por bloques de años",
            "regional_ratios": [{"pair": r.pair, "season": r.season,
                                 "ratio": clean_number(r.ratio, 4),
                                 "p10": clean_number(r.p10, 4), "p90": clean_number(r.p90, 4)}
                                for r in regional.itertuples()],
            "calib_window": [str(d) for d in hp.calib_window],
            "holdout_years": hp.holdout_years,
        },
        "validation": {
            "acceptance": metrics.get("acceptance"),
            "chains": {k: {"regional": v.get("regional"),
                           "band_coverage_out_of_sample":
                               v.get("band", {}).get("coverage_out_of_sample")}
                       for k, v in chains.items()},
        } if metrics else None,
        "reliability_thresholds": p.reliability.model_dump(exclude={"report_edges"}),
        "limits": {"max_aoi_km2": p.api.max_aoi_km2, "max_csv_years": p.api.max_csv_years,
                   "max_point_radius_km": p.api.max_point_radius_km,
                   "region_exempt_endpoints": ["/api/v1/calendar", "/api/v1/anomaly",
                                               "/api/v1/map/cells"]},
        "regions": sorted(repo.regions),
    }
