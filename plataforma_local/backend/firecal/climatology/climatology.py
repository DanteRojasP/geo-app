"""Climatología mensual de una serie: mediana, p25, p75, p90 por mes del año en ``base_years``.

Solo usa meses no provisionales dentro de ``base_years`` (inclusive).
"""

from __future__ import annotations

import pandas as pd


def base_sample(series: pd.DataFrame, base_years: tuple[int, int]) -> pd.DataFrame:
    """Filas de la serie que forman la climatología."""
    s = series[(series["year"] >= base_years[0]) & (series["year"] <= base_years[1])]
    if "provisional" in s.columns:
        s = s[~s["provisional"].astype(bool)]
    return s


def monthly_climatology(series: pd.DataFrame, base_years: tuple[int, int]) -> pd.DataFrame:
    """Por mes del año (1-12): median, p25, p75, p90 y n_years."""
    s = base_sample(series, base_years)
    rows = []
    for month in range(1, 13):
        v = s.loc[s["month"] == month, "value"]
        if v.empty:
            rows.append({"month": month, "median": None, "p25": None, "p75": None, "p90": None,
                         "n_years": 0})
            continue
        q = v.quantile([0.5, 0.25, 0.75, 0.9])
        rows.append({"month": month, "median": float(q[0.5]), "p25": float(q[0.25]),
                     "p75": float(q[0.75]), "p90": float(q[0.9]), "n_years": int(v.size)})
    return pd.DataFrame(rows)


def expected_annual(series: pd.DataFrame, base_years: tuple[int, int]) -> float | None:
    """Total anual esperado: media de los totales de los años COMPLETOS (12 meses) de la base."""
    s = base_sample(series, base_years)
    per_year = s.groupby("year")["value"].agg(["sum", "size"])
    full = per_year[per_year["size"] == 12]
    return float(full["sum"].mean()) if len(full) else None
