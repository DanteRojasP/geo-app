"""Percentiles de un valor dentro de la climatología de su mes del año.

- ``percentile_rank``: rango medio, 0-100 (empates cuentan la mitad).
- ``harmonized_percentiles``: percentil de cada mes de la serie armonizada en su mes del año.
- ``sensor_independent_percentiles``: percentil del conteo CRUDO de cada mes dentro de la
  climatología cruda de su propio satélite de referencia (el satélite fuente de ese mes). No depende
  de la armonización: sirve para comparar meses aunque cambie el sensor.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from firecal.climatology.aoi import HarmonizedData, _filter_cells, raw_series
from firecal.climatology.climatology import base_sample


def percentile_rank(value: float, sample) -> float | None:
    """Porcentaje de la muestra por debajo de ``value`` (empates cuentan la mitad)."""
    a = np.asarray(sample, dtype=float)
    if a.size == 0 or value is None or np.isnan(value):
        return None
    below = np.sum(a < value)
    equal = np.sum(a == value)
    return float(100.0 * (below + 0.5 * equal) / a.size)


def harmonized_percentiles(series: pd.DataFrame, base_years: tuple[int, int]) -> pd.Series:
    """Percentil de cada fila de ``series`` dentro de la base de su mes del año."""
    base = base_sample(series, base_years)
    samples = {m: base.loc[base["month"] == m, "value"].to_numpy() for m in range(1, 13)}
    return pd.Series([percentile_rank(v, samples[m])
                      for v, m in zip(series["value"], series["month"], strict=True)],
                     index=series.index, dtype="float")


def sensor_independent_percentiles(data: HarmonizedData, cells, base_years: tuple[int, int],
                                   min_years: int) -> pd.DataFrame:
    """year, month, satellite, raw_value, percentile (en la climatología cruda de su satélite).

    Base: años de ``base_years`` no provisionales en los que el satélite operó el mes completo; si
    son menos de ``min_years`` para ese mes del año, se usan todos los años disponibles del
    satélite (no provisionales). Para Aqua y Terra la base termina donde empieza su deriva
    orbital (``aqua_observed_until`` y fin de ``terra_aqua_window``).
    """
    hp = data.hp
    y, m = (int(x) for x in hp.aqua_observed_until.split("-"))
    valid_until = {"AQUA": y * 100 + m,
                   "TERRA": hp.terra_aqua_window[1].year * 100 + hp.terra_aqua_window[1].month}
    months = data.months[["year", "month", "satellite", "is_provisional"]]
    raw_aoi = _filter_cells(data.raw, cells)
    out = []
    for sat, mm in months.groupby("satellite"):
        current = raw_series(data, cells, sat, raw_aoi)  # valor de cada mes
        raw = current.copy()
        prov = set(zip(months.loc[months["is_provisional"], "year"],
                       months.loc[months["is_provisional"], "month"], strict=True))
        raw["provisional"] = [(y, m) in prov for y, m in
                              zip(raw["year"], raw["month"], strict=True)]
        if sat in valid_until:
            raw = raw[raw["year"] * 100 + raw["month"] <= valid_until[sat]]
        base = base_sample(raw, base_years)
        everything = raw[~raw["provisional"]]
        samples = {}
        for m in range(1, 13):
            b = base.loc[base["month"] == m, "value"]
            if b.size < min_years:
                b = everything.loc[everything["month"] == m, "value"]
            samples[m] = b.to_numpy()
        vals = mm[["year", "month"]].merge(current[["year", "month", "value"]],
                                           on=["year", "month"], how="left").fillna({"value": 0.0})
        vals["satellite"] = sat
        vals["percentile"] = [percentile_rank(v, samples[m])
                              for v, m in zip(vals["value"], vals["month"], strict=True)]
        out.append(vals.rename(columns={"value": "raw_value"}))
    res = pd.concat(out, ignore_index=True)
    return res.sort_values(["year", "month"], ignore_index=True)
