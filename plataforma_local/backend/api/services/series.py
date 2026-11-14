"""Calendario (matriz año x mes) y anomalía de un AOI."""

from __future__ import annotations

import numpy as np
import pandas as pd

from api.db import Repository
from api.services.common import (
    NOTE_ANDES,
    NOTE_DIURNAL,
    NOTE_H3,
    NOTE_LOW_CONF,
    NOTE_PROVISIONAL,
    NOTE_RELIABILITY_LOW,
    UNIT_HARMONIZED,
    AOIError,
    ResolvedAOI,
    clean_number,
    envelope,
    outside_note,
)
from firecal.climatology.anomaly import anomaly, reliability
from firecal.climatology.aoi import aoi_series, raw_series, raw_viirs_series
from firecal.climatology.climatology import expected_annual, monthly_climatology
from firecal.climatology.percentiles import (
    harmonized_percentiles,
    sensor_independent_percentiles,
)
from firecal.harmonization.data import parse_year_month

UNITS = {
    "harmonized": UNIT_HARMONIZED,
    "percentile": "percentil (0-100) del conteo crudo diurno en la climatología de su propio "
                  "satélite de referencia",
    "raw_modis": "focos crudos MODIS-Aqua diurno (sin armonizar)",
    "raw_viirs": "focos crudos VIIRS diurno (un satélite por mes: S-NPP, N20 o N21; sin armonizar)",
}
NOTE_RAW_MODIS = ("Modo crudo: Aqua deriva de su órbita desde ~2021; los años recientes no son "
                  "comparables con los antiguos.")
NOTE_RAW_VIIRS = ("Modo crudo: S-NPP, N20 y N21 no se suman; cambiar de satélite puede producir "
                  "saltos en la serie.")
NOTE_PERCENTILE = ("Modo percentil: independiente del sensor; compara cada mes con la historia "
                   "de su propio satélite.")


def _common(repo: Repository, aoi: ResolvedAOI) -> tuple[pd.DataFrame, float | None, str, list]:
    """Serie armonizada, conteo anual esperado, confiabilidad y avisos base."""
    p = repo.settings.params
    series = aoi_series(repo.data, aoi.cells)
    exp = expected_annual(series, p.climatology.base_years)
    rel = reliability(exp, p.reliability)
    notes = [NOTE_H3, NOTE_DIURNAL, NOTE_ANDES, *outside_note(repo, aoi)]
    if rel == "baja":
        notes.append(NOTE_RELIABILITY_LOW)
    return series, exp, rel, notes


def calendar(repo: Repository, aoi: ResolvedAOI, mode: str, start_year: int | None,
             end_year: int | None) -> dict:
    p = repo.settings.params
    base_years = p.climatology.base_years
    series, exp, rel, notes = _common(repo, aoi)
    start = start_year if start_year is not None else parse_year_month(
        p.harmonization.series_start)[0]
    end = end_year if end_year is not None else repo.last_month()[0]
    if start > end:
        raise AOIError(f"start_year ({start}) debe ser <= end_year ({end}).")

    if mode == "harmonized":
        out = series.copy()
        out["percentile"] = harmonized_percentiles(series, base_years)
        clim_series = series
    elif mode == "percentile":
        pct = sensor_independent_percentiles(repo.data, aoi.cells, base_years,
                                             p.climatology.percentile_min_years)
        out = series.drop(columns=["value"]).merge(
            pct[["year", "month", "percentile"]], on=["year", "month"], how="left")
        out["value"] = out["percentile"]
        out["band_p10"] = out["band_p90"] = np.nan
        clim_series = series
        notes.append(NOTE_PERCENTILE)
    else:
        raw = (raw_series(repo.data, aoi.cells, "AQUA") if mode == "raw_modis"
               else raw_viirs_series(repo.data, aoi.cells))
        flags = series[["year", "month", "provisional"]]
        out = raw.merge(flags, on=["year", "month"], how="left").fillna({"provisional": False})
        out["source"] = out["satellite"].str.lower() + "_raw"
        out["low_confidence"] = False
        out["band_p10"] = out["band_p90"] = np.nan
        out["percentile"] = harmonized_percentiles(out, base_years)
        clim_series = out
        notes.append(NOTE_RAW_MODIS if mode == "raw_modis" else NOTE_RAW_VIIRS)

    out = out[(out["year"] >= start) & (out["year"] <= end)]
    if out["provisional"].astype(bool).any():
        notes.append(NOTE_PROVISIONAL)
    if mode in ("harmonized", "percentile") and out["low_confidence"].astype(bool).any():
        notes.append(NOTE_LOW_CONF)

    cells = [{
        "year": int(r.year), "month": int(r.month), "value": clean_number(r.value),
        "band_p10": clean_number(r.band_p10), "band_p90": clean_number(r.band_p90),
        "percentile": clean_number(r.percentile, 1), "source": r.source,
        "satellite": r.satellite, "provisional": bool(r.provisional),
        "low_confidence": bool(r.low_confidence),
    } for r in out.itertuples()]
    clim = monthly_climatology(clim_series, base_years)
    return {
        **envelope(repo, notes),
        "unit": UNITS[mode], "mode": mode,
        "years": list(range(start, end + 1)), "months": list(range(1, 13)),
        "cells": cells,
        "climatology": [{"month": int(c.month), "median": clean_number(c.median),
                         "p25": clean_number(c.p25), "p75": clean_number(c.p75),
                         "p90": clean_number(c.p90), "n_years": int(c.n_years)}
                        for c in clim.itertuples()],
        "aoi": aoi.info(), "reliability": rel, "expected_annual": clean_number(exp, 1),
    }


def anomaly_report(repo: Repository, aoi: ResolvedAOI, year: int | None,
                   month: int | None) -> dict:
    p = repo.settings.params
    series, exp, rel, notes = _common(repo, aoi)
    if (year is None) != (month is None):
        raise AOIError("Indica year y month juntos, o ninguno (último mes con datos).")
    if year is None:
        year, month = repo.last_month()
    try:
        a = anomaly(series, year, month, p.climatology.base_years,
                    p.climatology.category_percentiles)
    except KeyError as exc:
        raise AOIError(f"No hay datos armonizados para {year}-{month:02d}.") from exc
    pct = sensor_independent_percentiles(repo.data, aoi.cells, p.climatology.base_years,
                                         p.climatology.percentile_min_years)
    ps = pct[(pct["year"] == year) & (pct["month"] == month)]["percentile"]
    if a.get("provisional"):
        notes.append(NOTE_PROVISIONAL)
    if a.get("low_confidence"):
        notes.append(NOTE_LOW_CONF)
    numeric = ("value", "band_p10", "band_p90", "median", "p25", "p75", "p90", "anomaly_abs",
               "anomaly_pct")
    return {
        **envelope(repo, notes), "unit": UNIT_HARMONIZED, "aoi": aoi.info(),
        "reliability": rel, "expected_annual": clean_number(exp, 1),
        **{k: (clean_number(a[k]) if k in numeric else a[k]) for k in a
           if k not in ("percentile",)},
        "percentile": clean_number(a["percentile"], 1),
        "percentile_sensor": clean_number(ps.iloc[0], 1) if len(ps) else None,
        "provisional": bool(a.get("provisional", False)),
        "low_confidence": bool(a.get("low_confidence", False)),
    }
