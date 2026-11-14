"""Anomalía de un mes frente a la climatología de su mes del año, y confiabilidad del AOI."""

from __future__ import annotations

import pandas as pd

from firecal.climatology.climatology import base_sample
from firecal.climatology.percentiles import percentile_rank
from firecal.settings import ReliabilityParams

CATEGORY_LABELS = ("muy por debajo", "por debajo", "normal", "por encima", "muy por encima")


def category(percentile: float | None, cuts: tuple[float, float, float, float]) -> str | None:
    """Categoría según ``climatology.category_percentiles`` (p. ej. 10, 25, 75, 90)."""
    if percentile is None:
        return None
    a, b, c, d = cuts
    if percentile < a:
        return CATEGORY_LABELS[0]
    if percentile < b:
        return CATEGORY_LABELS[1]
    if percentile <= c:
        return CATEGORY_LABELS[2]
    if percentile <= d:
        return CATEGORY_LABELS[3]
    return CATEGORY_LABELS[4]


def anomaly(series: pd.DataFrame, year: int, month: int, base_years: tuple[int, int],
            cuts: tuple[float, float, float, float]) -> dict:
    """Valor del mes, mediana histórica y anomalía (diferencia, %, percentil, categoría)."""
    row = series[(series["year"] == year) & (series["month"] == month)]
    if row.empty:
        raise KeyError(f"No hay datos para {year}-{month:02d}")
    r = row.iloc[0]
    base = base_sample(series, base_years)
    sample = base.loc[base["month"] == month, "value"]
    median = float(sample.median()) if len(sample) else None
    value = float(r["value"])
    pct = percentile_rank(value, sample.to_numpy())
    out = {
        "year": int(year), "month": int(month), "value": value,
        "median": median,
        "p25": float(sample.quantile(0.25)) if len(sample) else None,
        "p75": float(sample.quantile(0.75)) if len(sample) else None,
        "p90": float(sample.quantile(0.90)) if len(sample) else None,
        "n_years": int(len(sample)),
        "anomaly_abs": value - median if median is not None else None,
        "anomaly_pct": 100.0 * (value - median) / median if median else None,
        "percentile": pct,
        "category": category(pct, cuts),
    }
    for col in ("band_p10", "band_p90", "source", "satellite", "low_confidence", "provisional"):
        if col in r.index:
            v = r[col]
            out[col] = v.item() if hasattr(v, "item") else v
    return out


def reliability(expected_annual: float | None, params: ReliabilityParams) -> str:
    """'alta' / 'media' / 'baja' según el conteo anual esperado del AOI."""
    if expected_annual is None or expected_annual < params.expected_annual_low:
        return "baja"
    if expected_annual < params.expected_annual_high:
        return "media"
    return "alta"
