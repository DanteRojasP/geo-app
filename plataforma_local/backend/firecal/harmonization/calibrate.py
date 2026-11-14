"""Calibración por razón de sumas con estratos jerárquicos y bootstrap por bloques de años.

Para un par fuente -> referencia (p. ej. SNPP -> AQUA), en los meses elegibles:

    R_s = sum(referencia en el estrato s) / sum(fuente en el estrato s)

Estrato = celda padre H3 res 4 x temporada. Si un estrato no alcanza ``stratum_min_ref_focos``
focos de la referencia o ``stratum_min_years`` años con datos de la referencia, usa su celda padre
res 3 x temporada; si tampoco alcanza, el estrato regional de su temporada. Los estratos de nivel
superior agrupan a todos sus hijos.

Incertidumbre: se remuestrean años completos con reemplazo (B réplicas). Las mismas réplicas de
años se usan para todos los estratos de un par, así la banda de una suma de estratos es correcta.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from firecal.harmonization.data import REGION, DayCounts, counts_in_months
from firecal.settings import HarmonizationParams

log = logging.getLogger(__name__)
METHOD = "ratio_of_sums"


@dataclass
class Calibration:
    """Resultado de calibrar (o componer) un par."""

    pair: str
    assign: pd.DataFrame        # p4, season, estrato
    strata: pd.DataFrame        # estrato, level, season, ratio, p10, p90, n_ref, n_src, n_years
    boot: dict[str, np.ndarray]  # estrato -> réplicas (B,)
    window: str
    n_months: int

    def ratio_for(self, p4: pd.Series, season: pd.Series) -> tuple[pd.Series, pd.Series]:
        """(estrato, razón) para cada celda padre y temporada; padres sin calibrar -> regional."""
        key = pd.DataFrame({"p4": p4.to_numpy(), "season": season.to_numpy()})
        est = key.merge(self.assign, on=["p4", "season"], how="left")["estrato"]
        fallback = self.regional_estrato(key["season"])
        est = est.fillna(fallback).to_numpy()
        ratio = pd.Series(est).map(self.strata.set_index("estrato")["ratio"]).to_numpy()
        return pd.Series(est, index=p4.index), pd.Series(ratio, index=p4.index)

    def regional_estrato(self, season: pd.Series) -> pd.Series:
        """Estrato de respaldo (regional) para cada temporada."""
        reg = self.strata[self.strata["level"] == REGION].set_index("season")["estrato"]
        if reg.empty:  # par compuesto: el respaldo es el compuesto de los regionales
            reg = self.strata[self.strata["level"] == "region*region"].set_index("season")[
                "estrato"]
        return season.map(reg)


def _quantiles(boot: np.ndarray, hp: HarmonizationParams) -> tuple[float, float]:
    lo, hi = np.nanquantile(boot, hp.band_quantiles)
    return float(lo), float(hi)


def calibrate_pair(
    dc: DayCounts,
    pair: str,
    ref: str,
    src: str,
    months: list[tuple[int, int]],
    hp: HarmonizationParams,
    rng: np.random.Generator,
    bootstrap: bool = True,
) -> Calibration:
    """Calibra ``src -> ref`` con razón de sumas por estrato y bootstrap por años.

    ``bootstrap=False`` (ajustes auxiliares, p. ej. leave-one-year-out) deja una sola "réplica"
    igual a la razón puntual.
    """
    if not months:
        raise ValueError(f"{pair}: no hay meses elegibles para calibrar")
    keys = ["p4", "p3", "season", "year"]
    r = counts_in_months(dc, ref, months).groupby(keys)["n_focos"].sum().rename("ref")
    s = counts_in_months(dc, src, months).groupby(keys)["n_focos"].sum().rename("src")
    base = pd.concat([r, s], axis=1).fillna(0).reset_index()
    years = np.array(sorted({y for y, _ in months}))

    def level_table(col: str | None) -> pd.DataFrame:
        gk = ([col] if col else []) + ["season"]
        t = base.groupby(gk).agg(n_ref=("ref", "sum"), n_src=("src", "sum")).reset_index()
        ny = (base[base["ref"] > 0].groupby(gk)["year"].nunique().rename("n_years"))
        t = t.merge(ny.reset_index(), on=gk, how="left").fillna({"n_years": 0})
        t["valid"] = ((t["n_ref"] >= hp.stratum_min_ref_focos)
                      & (t["n_years"] >= hp.stratum_min_years) & (t["n_src"] > 0))
        t["estrato"] = (f"r{_res(col, hp)}:" + t[col] + "|" + t["season"]) if col else (
            REGION + "|" + t["season"])
        t["level"] = col or REGION
        return t

    t4, t3, treg = level_table("p4"), level_table("p3"), level_table(None)
    pairs = base[["p4", "p3", "season"]].drop_duplicates()
    pairs = pairs.merge(t4[["p4", "season", "valid", "estrato"]], on=["p4", "season"])
    pairs = pairs.merge(t3[["p3", "season", "valid", "estrato"]], on=["p3", "season"],
                        suffixes=("", "_3"))
    pairs = pairs.merge(treg[["season", "estrato"]], on="season", suffixes=("", "_reg"))
    pairs["chosen"] = np.where(pairs["valid"], pairs["estrato"],
                               np.where(pairs["valid_3"], pairs["estrato_3"],
                                        pairs["estrato_reg"]))
    assign = pairs[["p4", "season"]].assign(estrato=pairs["chosen"].to_numpy())

    # Estratos usados + siempre los regionales (respaldo para celdas nuevas).
    used = set(assign["estrato"]) | set(treg["estrato"])
    all_t = pd.concat([t4, t3, treg], ignore_index=True)
    strata = all_t[all_t["estrato"].isin(used)].copy()
    if (strata["n_src"] <= 0).any():
        bad = strata.loc[strata["n_src"] <= 0, "estrato"].tolist()
        raise ValueError(f"{pair}: estratos sin focos de la fuente: {bad}")

    # Matrices estrato x año para el bootstrap.
    member = {"p4": "p4", "p3": "p3", REGION: None}
    ref_m = np.zeros((len(strata), years.size))
    src_m = np.zeros((len(strata), years.size))
    by_year = {}
    for lvl, col in member.items():
        gk = ([col] if col else []) + ["season", "year"]
        by_year[lvl] = base.groupby(gk)[["ref", "src"]].sum()
    year_idx = {y: i for i, y in enumerate(years)}
    for i, row in enumerate(strata.itertuples()):
        tab = by_year[row.level]
        sub = (tab.xs((row.season,), level=["season"]) if row.level == REGION
               else tab.xs((getattr(row, row.level), row.season), level=[row.level, "season"]))
        for y, vals in sub.iterrows():
            ref_m[i, year_idx[y]] = vals["ref"]
            src_m[i, year_idx[y]] = vals["src"]

    B = hp.bootstrap_reps if bootstrap else 1
    draws = (rng.integers(0, years.size, (B, years.size)) if bootstrap
             else np.arange(years.size)[None, :])
    weights = np.zeros((B, years.size))
    np.add.at(weights, (np.repeat(np.arange(B), years.size), draws.ravel()), 1)
    num, den = weights @ ref_m.T, weights @ src_m.T
    point = ref_m.sum(axis=1) / src_m.sum(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        reps = np.where(den > 0, num / den, np.nan)
    reps = np.where(np.isnan(reps), point[None, :], reps)  # réplica sin fuente -> punto

    strata["ratio"] = point
    q = np.quantile(reps, hp.band_quantiles, axis=0)
    strata["p10"], strata["p90"] = q[0], q[1]
    strata = strata.drop(columns=["valid", "p4", "p3"], errors="ignore")
    strata = strata[["estrato", "level", "season", "ratio", "p10", "p90", "n_ref", "n_src",
                     "n_years"]].reset_index(drop=True)
    boot = {e: reps[:, i] for i, e in enumerate(strata["estrato"])}
    window = f"{months[0][0]}-{months[0][1]:02d}..{months[-1][0]}-{months[-1][1]:02d}"
    n_by_level = assign["estrato"].str.split(":").str[0].str.split("|").str[0].value_counts()
    (log.info if bootstrap else log.debug)(
        "%s: %d meses (%s), estratos por nivel %s, razon regional %s", pair,
        len(months),
             window, n_by_level.to_dict(),
             {r.season: round(r.ratio, 4) for r in strata[strata["level"] == REGION].itertuples()})
    return Calibration(pair, assign, strata, boot, window, len(months))


def _res(col: str | None, hp: HarmonizationParams) -> int:
    return {"p4": 4, "p3": hp.h3_res_calibration_mid}.get(col, 0) if col else 0


def compose(outer: Calibration, inner: Calibration, pair: str,
            hp: HarmonizationParams) -> Calibration:
    """Compone dos calibraciones: fuente -> intermedio (``outer``) y intermedio -> ref (``inner``).

    R = R_outer x R_inner por celda padre y temporada; réplicas: producto réplica a réplica.
    """
    keys = pd.concat([outer.assign[["p4", "season"]], inner.assign[["p4", "season"]]])
    keys = keys.drop_duplicates().reset_index(drop=True)
    e_out, _ = outer.ratio_for(keys["p4"], keys["season"])
    e_in, _ = inner.ratio_for(keys["p4"], keys["season"])
    keys["estrato"] = e_out.to_numpy() + " * " + e_in.to_numpy()

    # Respaldo regional compuesto (para celdas que ninguna calibración vio).
    reg_rows = []
    for season in sorted(keys["season"].unique()):
        s = pd.Series([season])
        reg_rows.append((outer.regional_estrato(s).iloc[0] + " * "
                         + inner.regional_estrato(s).iloc[0], season))
    combos = {e: (e.split(" * ")[0], e.split(" * ")[1]) for e in keys["estrato"]}
    combos.update({e: (e.split(" * ")[0], e.split(" * ")[1]) for e, _ in reg_rows})
    reg_names = {e for e, _ in reg_rows}

    o_ratio = outer.strata.set_index("estrato")["ratio"]
    i_ratio = inner.strata.set_index("estrato")["ratio"]
    rows, boot = [], {}
    for est, (eo, ei) in combos.items():
        reps = outer.boot[eo] * inner.boot[ei]
        boot[est] = reps
        lo, hi = _quantiles(reps, hp)
        season = est.rsplit("|", 1)[-1]
        rows.append({"estrato": est, "level": "region*region" if est in reg_names else "compuesto",
                     "season": season, "ratio": float(o_ratio[eo] * i_ratio[ei]), "p10": lo,
                     "p90": hi, "n_ref": np.nan, "n_src": np.nan, "n_years": np.nan})
    strata = pd.DataFrame(rows)
    return Calibration(pair, keys, strata, boot, f"{outer.window} x {inner.window}",
                       min(outer.n_months, inner.n_months))


def params_table(cal: Calibration, version: str) -> pd.DataFrame:
    t = cal.strata.copy()
    t.insert(0, "pair", cal.pair)
    t["method"] = METHOD
    t["window"] = cal.window
    t["n_months"] = cal.n_months
    t["version"] = version
    return t


def bootstrap_table(cal: Calibration) -> pd.DataFrame:
    parts = [pd.DataFrame({"pair": cal.pair, "estrato": e, "rep": np.arange(r.size), "ratio": r})
             for e, r in cal.boot.items()]
    return pd.concat(parts, ignore_index=True)
