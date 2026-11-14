"""Limpieza de focos normalizados.

Orden de los pasos (cada uno cuenta lo que quita, por satélite, en el reporte):

1. ``duplicates``: filas idénticas (satélite, hora, posición).
2. ``nrt_superseded``: si un satélite tiene datos SP, se quitan sus NRT con hora <= al último SP
   (el SP reemplaza al NRT).
3. ``bowtie``: MODIS, misma pasada (satélite + hora) y a < ``bowtie_max_km``: se conserva el de
   mayor confianza/FRP.
4. ``outside_region``: fuera de la región + ``region.buffer_km`` (buffer en UTM con pyproj).
5. Fuentes fijas: celdas ~1 km (``px1km_id``) con detecciones en más de
   ``static_source_month_fraction`` de los meses -> ``is_static = True``. Se calcula con TODAS
   las filas que quedan tras 1-4 (incluidas las ``type != 0``), para que una fuente industrial
   marcada en SP también quede marcada en el periodo NRT, que no trae ``type``. Estas filas se
   conservan en ``hotspots`` con la marca, y se excluyen de todo cálculo posterior.
6. ``non_vegetation_type``: ``type`` distinto de 0 cuando existe.
7. ``low_confidence``: confianza por debajo de ``min_confidence``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.base import BaseGeometry

from firecal.etl.firms_schema import FIRMS_ASSUMPTIONS, is_nrt_version
from firecal.grid.px1km import px1km_id
from firecal.regions import buffer_km
from firecal.settings import ScientificParams

log = logging.getLogger(__name__)

KM_PER_DEG_LAT = 111.32
CONFIDENCE_ORDER = {"low": 0, "nominal": 1, "high": 2}


@dataclass
class CleanReport:
    """Filas quitadas (o marcadas) por paso y por satélite."""

    n_input: int = 0
    n_output: int = 0
    n_static: int = 0
    removed: dict[str, dict[str, int]] = field(default_factory=dict)
    static_cells: int = 0
    n_months: int = 0

    def record(self, step: str, dropped: pd.DataFrame) -> None:
        self.removed[step] = {str(k): int(v) for k, v in
                              dropped["satellite"].value_counts().sort_index().items()}
        log.info("Limpieza %-20s: %d filas", step, len(dropped))

    def to_dict(self) -> dict:
        return {"n_input": self.n_input, "n_output": self.n_output, "n_static": self.n_static,
                "static_cells": self.static_cells, "n_months": self.n_months,
                "removed": self.removed}


def _drop(df: pd.DataFrame, mask: pd.Series, step: str, report: CleanReport) -> pd.DataFrame:
    report.record(step, df[mask])
    return df[~mask]


def drop_superseded_nrt(df: pd.DataFrame) -> pd.Series:
    """Máscara de filas NRT cubiertas por SP del mismo satélite (hora <= último SP)."""
    nrt = df["version"].map(is_nrt_version).astype(bool)
    last_sp = df[~nrt].groupby("satellite")["acq_utc"].max()
    limit = df["satellite"].map(last_sp)
    return nrt & limit.notna() & (df["acq_utc"] <= limit)


def bowtie_duplicates(df: pd.DataFrame, max_km: float) -> pd.Series:
    """Máscara de duplicados bow-tie MODIS (misma pasada, < ``max_km`` de uno mejor)."""
    modis = df[df["sensor"] == "MODIS"]
    mask = pd.Series(False, index=df.index)
    if modis.empty:
        return mask
    key = ["satellite", "acq_utc"]
    sizes = modis.groupby(key)["id"].transform("size")
    cand = modis[sizes > 1]
    if cand.empty:
        return mask
    conf = pd.to_numeric(cand["confidence_raw"], errors="coerce").fillna(-1)
    ranked = cand.assign(_conf=conf, _frp=cand["frp"].fillna(-1))
    # rango: mayor confianza, luego mayor FRP, luego menor id -> rango 0 es el mejor
    ranked = ranked.sort_values(["_conf", "_frp", "id"], ascending=[False, False, True])
    ranked["_rank"] = np.arange(len(ranked))
    cols = [*key, "id", "lat", "lon", "_rank"]
    pairs = ranked[cols].merge(ranked[cols], on=key, suffixes=("_a", "_b"))
    pairs = pairs[pairs["_rank_a"] < pairs["_rank_b"]]  # a es mejor que b
    dy = (pairs["lat_b"] - pairs["lat_a"]) * KM_PER_DEG_LAT
    dx = (pairs["lon_b"] - pairs["lon_a"]) * KM_PER_DEG_LAT * np.cos(np.deg2rad(pairs["lat_a"]))
    close = np.hypot(dx, dy) < max_km
    dup_ids = set(pairs.loc[close, "id_b"])
    mask.loc[df["id"].isin(dup_ids)] = True
    return mask


def outside_region(df: pd.DataFrame, region: BaseGeometry, buffer: float) -> pd.Series:
    """Máscara de filas fuera de la región con buffer (prefiltro por bbox + punto en polígono)."""
    geom = buffer_km(region, buffer)
    w, s, e, n = geom.bounds
    in_bbox = df["lon"].between(w, e) & df["lat"].between(s, n)
    inside = pd.Series(False, index=df.index)
    sub = df[in_bbox]
    shapely.prepare(geom)
    inside.loc[sub.index] = shapely.contains_xy(geom, sub["lon"].to_numpy(),
                                                sub["lat"].to_numpy())
    return ~inside


def static_cells(df: pd.DataFrame, fraction: float) -> tuple[set[int], int]:
    """Celdas ~1 km con detecciones en más de ``fraction`` de los meses del periodo."""
    month = df["local_date"].dt.to_period("M")
    n_months = (month.max() - month.min()).n + 1
    months_per_cell = (pd.DataFrame({"px": df["px1km_id"], "m": month})
                       .drop_duplicates().groupby("px").size())
    static = set(months_per_cell[months_per_cell / n_months > fraction].index)
    return static, int(n_months)


def clean_hotspots(df: pd.DataFrame, region: BaseGeometry,
                   params: ScientificParams) -> tuple[pd.DataFrame, CleanReport]:
    """Aplica todos los pasos de limpieza. Devuelve (focos limpios con is_static, reporte)."""
    f = params.filters
    report = CleanReport(n_input=len(df))
    df = df.copy()

    dup = df.duplicated(["satellite", "acq_utc", "lat", "lon"], keep="first")
    df = _drop(df, dup, "duplicates", report)
    df = _drop(df, drop_superseded_nrt(df), "nrt_superseded", report)
    df = _drop(df, bowtie_duplicates(df, f.bowtie_max_km), "bowtie", report)
    df = _drop(df, outside_region(df, region, params.region.buffer_km), "outside_region", report)

    df["px1km_id"] = px1km_id(df["lat"].to_numpy(), df["lon"].to_numpy(), params.grid.px1km_deg)
    static, n_months = static_cells(df, f.static_source_month_fraction)
    df["is_static"] = df["px1km_id"].isin(static)
    report.static_cells, report.n_months = len(static), n_months

    veg = FIRMS_ASSUMPTIONS["type_vegetation"]
    non_veg = df["type"].notna() & (df["type"] != veg)
    df = _drop(df, non_veg.fillna(False), "non_vegetation_type", report)
    min_level = CONFIDENCE_ORDER[f.min_confidence]
    low = df["confidence_cat"].map(CONFIDENCE_ORDER) < min_level
    df = _drop(df, low, "low_confidence", report)

    report.n_static = int(df["is_static"].sum())
    report.n_output = len(df)
    log.info("Limpieza: %d -> %d filas (%d marcadas como fuente fija en %d celdas de ~1 km)",
             report.n_input, report.n_output, report.n_static, report.static_cells)
    return df.reset_index(drop=True), report
