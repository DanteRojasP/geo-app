"""Calibración de producción y ensamblado de ``harmonized_monthly``.

Unidad: focos equivalentes a MODIS-Aqua DIURNO por celda H3 y mes local.

Fuente por mes (igual para todas las celdas; ver ``month_plan``):
- antes del primer mes completo de Aqua -> ``terra_adjusted`` (Terra D x R_TERRA->AQUA,
  ``low_confidence``);
- hasta ``aqua_observed_until`` -> ``modis_observed`` (Aqua D tal cual);
- después -> ``viirs_converted``: S-NPP si operó el mes completo; si no N20 (R_N20->SNPP x
  R_SNPP->AQUA); si no N21 como respaldo (``low_confidence``).
Las tablas son dispersas: celda-mes sin fila = 0 focos (si el mes tiene fuente en
``harmonized_months``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from firecal.harmonization.calibrate import Calibration, calibrate_pair, compose
from firecal.harmonization.data import (
    DayCounts,
    eligible_months,
    first_full_month,
    is_full_month,
    parse_year_month,
    provisional_months,
)
from firecal.settings import HarmonizationParams

log = logging.getLogger(__name__)

MODIS_OBSERVED, VIIRS_CONVERTED, TERRA_ADJUSTED = "modis_observed", "viirs_converted", \
    "terra_adjusted"
PAIR_SEEDS = {"SNPP->AQUA": 1, "N20->SNPP": 2, "N21->SNPP": 3, "TERRA->AQUA": 4}
# (satélite fuente, par aplicado, low_confidence) en orden de preferencia tras Aqua observado.
VIIRS_PREFERENCE = (("SNPP", "SNPP->AQUA", False), ("N20", "N20->AQUA", False),
                    ("N21", "N21->AQUA", True))


def pair_rng(hp: HarmonizationParams, pair: str, salt: int = 0) -> np.random.Generator:
    """Generador reproducible por par (no depende del orden de ejecución)."""
    return np.random.default_rng([hp.bootstrap_seed, PAIR_SEEDS[pair], salt])


@dataclass
class ProductionCalibrations:
    cals: dict[str, Calibration]

    def __getitem__(self, pair: str) -> Calibration:
        return self.cals[pair]

    def __contains__(self, pair: str) -> bool:
        return pair in self.cals


def _try_calibrate(dc, pair, ref, src, window, hp, exclude=None) -> Calibration | None:
    months = eligible_months(dc, (ref, src), window, hp, exclude_years=exclude)
    if not months:
        log.warning("%s: sin meses elegibles en %s; el par no se calibra", pair, window)
        return None
    return calibrate_pair(dc, pair, ref, src, months, hp, pair_rng(hp, pair, int(bool(exclude))))


def fit_calibrations(dc: DayCounts, hp: HarmonizationParams,
                     exclude_years: set[int] | None = None) -> ProductionCalibrations:
    """Calibra los pares base y compone N20->AQUA y N21->AQUA."""
    cals: dict[str, Calibration] = {}
    specs = [("SNPP->AQUA", "AQUA", "SNPP", hp.calib_window),
             ("N20->SNPP", "SNPP", "N20", hp.n20_snpp_window),
             ("N21->SNPP", "SNPP", "N21", hp.n21_snpp_window),
             ("TERRA->AQUA", "AQUA", "TERRA", hp.terra_aqua_window)]
    for pair, ref, src, window in specs:
        cal = _try_calibrate(dc, pair, ref, src, window, hp, exclude_years)
        if cal is not None:
            cals[pair] = cal
    if "SNPP->AQUA" not in cals:
        raise RuntimeError("No se pudo calibrar SNPP->AQUA: es la base de toda la cadena")
    for src in ("N20", "N21"):
        if f"{src}->SNPP" in cals:
            cals[f"{src}->AQUA"] = compose(cals[f"{src}->SNPP"], cals["SNPP->AQUA"],
                                           f"{src}->AQUA", hp)
    return ProductionCalibrations(cals)


def month_plan(dc: DayCounts, cals: ProductionCalibrations,
               hp: HarmonizationParams) -> pd.DataFrame:
    """Fuente de cada mes, desde el primer mes con datos hasta el último."""
    ym = int((dc.counts["year"] * 100 + dc.counts["month"]).min())
    first_ym = (ym // 100, ym % 100)
    aqua_first = first_full_month("AQUA", hp)
    aqua_until = parse_year_month(hp.aqua_observed_until)
    prov = {s: provisional_months(dc, s) for s in hp.satellite_periods}
    rows = []
    y, m = first_ym
    while (y, m) <= dc.last_month:
        choice = None
        if (y, m) < aqua_first:
            if is_full_month("TERRA", y, m, hp) and "TERRA->AQUA" in cals:
                choice = (TERRA_ADJUSTED, "TERRA", "TERRA->AQUA", True)
        elif (y, m) <= aqua_until:
            if is_full_month("AQUA", y, m, hp):
                choice = (MODIS_OBSERVED, "AQUA", None, False)
        else:
            for sat, pair, low in VIIRS_PREFERENCE:
                if is_full_month(sat, y, m, hp) and pair in cals:
                    choice = (VIIRS_CONVERTED, sat, pair, low)
                    break
        if choice is None:
            log.warning("Mes %d-%02d sin fuente armonizable; se omite", y, m)
        else:
            source, sat, pair, low = choice
            rows.append({"year": y, "month": m, "source": source, "satellite": sat,
                         "pair": pair, "low_confidence": low,
                         "is_provisional": (y, m) in prov[sat]})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return pd.DataFrame(rows)


def assemble(dc: DayCounts, cals: ProductionCalibrations, plan: pd.DataFrame,
             version: str) -> pd.DataFrame:
    """Filas de ``harmonized_monthly`` (solo celda-mes con focos de la fuente del mes)."""
    rows = dc.counts.merge(plan, on=["year", "month", "satellite"], how="inner")
    rows = rows.rename(columns={"n_focos": "raw_value"})
    rows["raw_value"] = rows["raw_value"].astype(float)
    rows["value"], rows["p10"], rows["p90"] = rows["raw_value"], rows["raw_value"], \
        rows["raw_value"]
    rows["estrato"] = None
    for pair, idx in rows[rows["pair"].notna()].groupby("pair").groups.items():
        cal = cals[pair]
        sub = rows.loc[idx]
        est, ratio = cal.ratio_for(sub["p4"], sub["season"])
        q = cal.strata.set_index("estrato")
        rows.loc[idx, "estrato"] = est.to_numpy()
        rows.loc[idx, "value"] = ratio.to_numpy() * sub["raw_value"].to_numpy()
        rows.loc[idx, "p10"] = est.map(q["p10"]).to_numpy() * sub["raw_value"].to_numpy()
        rows.loc[idx, "p90"] = est.map(q["p90"]).to_numpy() * sub["raw_value"].to_numpy()
    rows["version"] = version
    cols = ["h3", "year", "month", "value", "p10", "p90", "raw_value", "source", "satellite",
            "pair", "estrato", "low_confidence", "is_provisional", "version"]
    return rows[cols].sort_values(["year", "month", "h3"], ignore_index=True)
