"""Datos de entrada de la armonización: conteos DIURNOS por celda-mes y reglas de meses.

Solo se usan pasadas diurnas (``daynight = 'D'``): la unidad de salida son focos equivalentes a
MODIS-Aqua diurno. Las detecciones nocturnas no entran al calendario armonizado.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

import duckdb
import h3
import pandas as pd

from firecal.settings import HarmonizationParams

DRY, WET = "seca", "humeda"
REGION = "region"


def season_of(month: int | pd.Series, dry_months: list[int]):
    """'seca' si el mes está en ``dry_season_months``; si no, 'humeda'."""
    if isinstance(month, pd.Series):
        return month.isin(dry_months).map({True: DRY, False: WET})
    return DRY if month in dry_months else WET


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def is_full_month(sat: str, year: int, month: int, hp: HarmonizationParams) -> bool:
    """El satélite operó el mes completo (para el mes en curso basta con que siga activo)."""
    start, end = hp.satellite_periods[sat]
    first, last = month_bounds(year, month)
    return start <= first and (end is None or end >= last)


def first_full_month(sat: str, hp: HarmonizationParams) -> tuple[int, int]:
    start, _ = hp.satellite_periods[sat]
    if start.day == 1:
        return start.year, start.month
    nxt = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return nxt.year, nxt.month


def parse_year_month(text: str) -> tuple[int, int]:
    y, m = text.split("-")
    return int(y), int(m)


@dataclass
class DayCounts:
    """Conteos diurnos por (h3, año, mes, satélite) + metadatos por satélite-mes."""

    counts: pd.DataFrame       # h3, p4, p3, year, month, season, satellite, n_focos, n_px1km
    provisional: pd.DataFrame  # satellite, year, month, is_provisional (meses con datos)
    cells: pd.DataFrame        # h3, p4, p3
    last_month: tuple[int, int]


def load_day_counts(con: duckdb.DuckDBPyConnection, hp: HarmonizationParams) -> DayCounts:
    cells = con.execute("SELECT h3, parent_calib AS p4 FROM cells").df()
    mid = hp.h3_res_calibration_mid
    p3 = {p: h3.cell_to_parent(p, mid) for p in cells["p4"].unique()}
    cells["p3"] = cells["p4"].map(p3)
    counts = con.execute("""
        SELECT h3, year, month, satellite, n_focos, n_px1km
        FROM monthly_counts WHERE daynight = 'D'
    """).df()
    counts = counts.merge(cells, on="h3", how="left")
    counts["season"] = season_of(counts["month"], hp.dry_season_months)
    prov = con.execute("""
        SELECT satellite, year, month, bool_or(is_provisional) AS is_provisional
        FROM monthly_counts GROUP BY ALL
    """).df()
    last = con.execute("SELECT max(year * 100 + month) FROM monthly_counts").fetchall()[0][0]
    return DayCounts(counts, prov, cells, (last // 100, last % 100))


def provisional_months(dc: DayCounts, sat: str) -> set[tuple[int, int]]:
    p = dc.provisional
    p = p[(p["satellite"] == sat) & p["is_provisional"]]
    return set(zip(p["year"], p["month"], strict=True))


def eligible_months(
    dc: DayCounts,
    sats: tuple[str, ...],
    window: tuple[date, date],
    hp: HarmonizationParams,
    exclude_years: set[int] | None = None,
    only_years: set[int] | None = None,
) -> list[tuple[int, int]]:
    """Meses completos dentro de la ventana, con todos los satélites operando el mes entero,
    sin datos provisionales (NRT) en ninguno y hasta el último mes con datos."""
    exclude_years = exclude_years or set()
    prov = set().union(*(provisional_months(dc, s) for s in sats))
    out = []
    y, m = window[0].year, window[0].month
    while (y, m) <= dc.last_month:
        first, last = month_bounds(y, m)
        if last > window[1]:
            break
        ok = (first >= window[0] and y not in exclude_years
              and (only_years is None or y in only_years)
              and all(is_full_month(s, y, m, hp) for s in sats) and (y, m) not in prov)
        if ok:
            out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def counts_in_months(dc: DayCounts, sat: str, months: list[tuple[int, int]]) -> pd.DataFrame:
    c = dc.counts
    c = c[c["satellite"] == sat]
    key = c["year"] * 100 + c["month"]
    return c[key.isin({y * 100 + m for y, m in months})]
