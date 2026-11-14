"""Series mensuales de un AOI (conjunto de celdas H3), calculadas al vuelo.

- ``aoi_series``: serie armonizada (focos equivalentes a Aqua DIURNO) con banda
  ``band_p10``/``band_p90``. Los meses con fuente pero sin focos en el AOI valen 0.
- ``raw_series``: conteo crudo diurno de un satélite (sin armonizar), solo en meses que operó
  completos.

Banda (ver ``firecal.harmonization.band``): para cada mes convertido se suman las réplicas del
bootstrap sobre los estratos del AOI y se ensancha con el error observado usando el conteo
predicho del AOI COMPLETO.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from firecal.harmonization.band import factor_band, widen
from firecal.harmonization.data import is_full_month
from firecal.settings import HarmonizationParams

SERIES_COLUMNS = ["year", "month", "value", "band_p10", "band_p90", "raw_value", "source",
                  "satellite", "pair", "low_confidence", "provisional"]


@dataclass
class HarmonizedData:
    """Tablas que necesitan los cálculos por AOI (las carga ``api.db.Repository``)."""

    harmonized: pd.DataFrame          # h3, year, month, value, raw_value, pair, estrato
    months: pd.DataFrame              # year, month, source, satellite, pair, low_confidence,
    #                                   is_provisional
    raw: pd.DataFrame                 # h3, year, month, satellite, n_focos  (solo diurno)
    boot: dict[str, dict[str, np.ndarray]]   # par -> estrato -> réplicas
    error_models: dict[str, pd.DataFrame]    # par -> modelo de error (solo si se aplica)
    hp: HarmonizationParams


def _filter_cells(df: pd.DataFrame, cells) -> pd.DataFrame:
    """Filas de ``df`` cuyas celdas están en ``cells``.

    Si ``h3`` es categórica (como la carga ``Repository``), filtra por códigos enteros: mucho más
    rápido que comparar texto cuando el AOI tiene decenas de miles de celdas.
    """
    col = df["h3"]
    if isinstance(col.dtype, pd.CategoricalDtype):
        idx = col.cat.categories.get_indexer(pd.Index(cells))
        return df[np.isin(col.cat.codes.to_numpy(), idx[idx >= 0])]
    return df[col.isin(set(cells))]


def aoi_series(data: HarmonizedData, cells) -> pd.DataFrame:
    """Serie armonizada mensual del AOI, un registro por mes de ``harmonized_months``."""
    hp = data.hp
    rows = _filter_cells(data.harmonized, cells)
    sums = rows.groupby(["year", "month"])[["value", "raw_value"]].sum()
    out = data.months.merge(sums.reset_index(), on=["year", "month"], how="left")
    out[["value", "raw_value"]] = out[["value", "raw_value"]].fillna(0.0)
    out["band_p10"], out["band_p90"] = out["value"], out["value"]  # observado: sin banda

    conv = rows[rows["pair"].notna()]
    for pair, g in conv.groupby("pair"):
        groups = g.groupby(["year", "month", "estrato"])["raw_value"].sum().reset_index()
        fb = factor_band(groups, ["year", "month"], data.boot[pair], hp.band_quantiles)
        idx = out.set_index(["year", "month"]).index
        sel = idx.isin(pd.MultiIndex.from_frame(fb[["year", "month"]]))
        merged = out.loc[sel, ["year", "month", "value"]].merge(fb, on=["year", "month"])
        lo, hi = widen(merged["value"], merged["factor_p10"], merged["factor_p90"],
                       data.error_models.get(pair), hp)
        out.loc[sel, "band_p10"] = lo
        out.loc[sel, "band_p90"] = hi
    # Meses convertidos sin focos de la fuente en el AOI: la banda también depende del error.
    zero_conv = out["pair"].notna() & (out["raw_value"] == 0)
    for pair, idx in out[zero_conv].groupby("pair").groups.items():
        lo, hi = widen(np.zeros(len(idx)), np.zeros(len(idx)), np.zeros(len(idx)),
                       data.error_models.get(pair), hp)
        out.loc[idx, "band_p10"], out.loc[idx, "band_p90"] = lo, hi
    out = out.rename(columns={"is_provisional": "provisional"})
    return out[SERIES_COLUMNS].sort_values(["year", "month"], ignore_index=True)


def raw_series(data: HarmonizedData, cells, satellite: str,
               raw_aoi: pd.DataFrame | None = None) -> pd.DataFrame:
    """Conteo crudo diurno del AOI para ``satellite`` en los meses que operó completos.

    ``raw_aoi``: ``data.raw`` ya filtrado por las celdas del AOI (evita repetir el filtro).
    """
    months = data.months[["year", "month"]]
    full = months[[is_full_month(satellite, y, m, data.hp)
                   for y, m in zip(months["year"], months["month"], strict=True)]]
    r = raw_aoi if raw_aoi is not None else _filter_cells(data.raw, cells)
    r = r[r["satellite"] == satellite].groupby(["year", "month"])["n_focos"].sum()
    out = full.merge(r.rename("value").reset_index(), on=["year", "month"], how="left")
    out["value"] = out["value"].fillna(0.0)
    out["satellite"] = satellite
    return out.reset_index(drop=True)


VIIRS_ORDER = ("SNPP", "N20", "N21")


def raw_viirs_series(data: HarmonizedData, cells) -> pd.DataFrame:
    """VIIRS crudo diurno: por mes, un solo satélite (S-NPP > N20 > N21), nunca sumados."""
    parts = []
    taken: set[tuple[int, int]] = set()
    raw_aoi = _filter_cells(data.raw, cells)
    for sat in VIIRS_ORDER:
        s = raw_series(data, cells, sat, raw_aoi)
        key = list(zip(s["year"], s["month"], strict=True))
        s = s[[k not in taken for k in key]]
        taken |= set(zip(s["year"], s["month"], strict=True))
        parts.append(s)
    out = pd.concat(parts, ignore_index=True)
    return out.sort_values(["year", "month"], ignore_index=True)
