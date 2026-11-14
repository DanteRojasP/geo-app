"""Validación de la armonización con años reservados (``holdout_years``).

Para cada cadena (S-NPP -> Aqua, N20 -> S-NPP -> Aqua, Terra -> Aqua) se calibra SIN los años
reservados y se predice Aqua diurno en esos años. Se reporta:

- serie regional mensual: MAE, sesgo relativo, Spearman, coincidencia de los 3 meses más activos;
- métricas por celda padre H3 res 4 (mediana y peor caso);
- sesgo relativo por nivel de actividad ESPERADO del mes (terciles: bajo, medio, alto). El nivel
  es la media de Aqua en ese mes del año (y celda padre) en años no reservados: clasificar por el
  valor observado del propio mes sesgaría el resultado (regresión a la media);
- cobertura de la banda del factor y, si hace falta, de la banda ensanchada con el error observado;
- método de contraste (regresión log1p con corrección de Duan), solo S-NPP -> Aqua;
- en modo sintético: comparación con la verdad del simulador.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from firecal.harmonization.apply import ProductionCalibrations, fit_calibrations
from firecal.harmonization.band import coverage, factor_band, fit_error_model, widen
from firecal.harmonization.calibrate import Calibration, calibrate_pair
from firecal.harmonization.data import DayCounts, counts_in_months, eligible_months
from firecal.settings import HarmonizationParams

log = logging.getLogger(__name__)

# cadena -> (satélite fuente, par aplicado)
CHAINS = {"SNPP->AQUA": ("SNPP", "SNPP->AQUA"),
          "N20->SNPP->AQUA": ("N20", "N20->AQUA"),
          "TERRA->AQUA": ("TERRA", "TERRA->AQUA")}
ACTIVITY_LABELS = ["bajo", "medio", "alto"]


@dataclass
class ChainValidation:
    chain: str
    pair: str
    cal: Calibration
    cells: pd.DataFrame    # h3, p4, year, month, season, obs, raw_value, estrato, pred
    units_r4: pd.DataFrame  # p4, year, month, obs, pred, factor_p10, factor_p90
    region: pd.DataFrame    # year, month, obs, pred, raw_value, factor_p10, factor_p90


# --------------------------------------------------------------------------------------
# Métricas
# --------------------------------------------------------------------------------------
def series_metrics(df: pd.DataFrame) -> dict:
    """Métricas de una serie mensual con columnas year, month, obs, pred."""
    obs, pred = df["obs"].to_numpy(float), df["pred"].to_numpy(float)
    tot = obs.sum()
    top = []
    for _, g in df.groupby("year"):
        if len(g) >= 3:
            a = set(g.nlargest(3, "obs")["month"])
            b = set(g.nlargest(3, "pred")["month"])
            top.append(len(a & b) / 3)
    return {
        "n_months": int(len(df)),
        "mae": float(np.mean(np.abs(pred - obs))) if len(df) else None,
        "mae_rel": float(np.mean(np.abs(pred - obs)) / np.mean(obs)) if tot > 0 else None,
        "bias_rel": float((pred.sum() - tot) / tot) if tot > 0 else None,
        "spearman": float(pd.Series(obs).corr(pd.Series(pred), method="spearman"))
        if len(df) > 2 and obs.std() > 0 and pred.std() > 0 else None,
        "top3_overlap": float(np.mean(top)) if top else None,
    }


def _summary(values: pd.Series, worst: str) -> dict:
    v = values.dropna()
    if v.empty:
        return {"median": None, "worst": None}
    w = {"max_abs": v.loc[v.abs().idxmax()], "min": v.min(), "max": v.max()}[worst]
    return {"median": float(v.median()), "worst": float(w)}


def by_unit_metrics(units: pd.DataFrame, min_focos: int) -> dict:
    rows = []
    for p4, g in units.groupby("p4"):
        if g["obs"].sum() >= min_focos:
            rows.append({"p4": p4, **series_metrics(g)})
    t = pd.DataFrame(rows)
    if t.empty:
        return {"n_units": 0}
    return {"n_units": int(len(t)), "min_focos_obs": min_focos,
            "bias_rel": _summary(t["bias_rel"], "max_abs"),
            "mae_rel": _summary(t["mae_rel"], "max"),
            "spearman": _summary(t["spearman"], "min"),
            "top3_overlap": _summary(t["top3_overlap"], "min")}


def bias_by_activity(units: pd.DataFrame) -> dict:
    """Sesgo relativo por terciles del nivel de actividad esperado (columna ``activity``)."""
    if len(units) < 3:
        return {}
    level = pd.qcut(units["activity"].rank(method="first"), 3, labels=ACTIVITY_LABELS)
    out = {}
    for lab, g in units.groupby(level, observed=True):
        tot = g["obs"].sum()
        out[str(lab)] = {"n": int(len(g)),
                         "activity_range": [float(g["activity"].min()),
                                            float(g["activity"].max())],
                         "obs_total": float(tot), "pred_total": float(g["pred"].sum()),
                         "bias_rel": float((g["pred"].sum() - tot) / tot) if tot else None}
    return out


def expected_activity(dc: DayCounts, hp: HarmonizationParams) -> tuple[pd.Series, pd.Series]:
    """Media de Aqua D por (celda padre, mes del año) y regional por mes del año, en los meses
    de ``calib_window`` fuera de los años reservados."""
    months = eligible_months(dc, ("AQUA",), hp.calib_window, hp,
                             exclude_years=set(hp.holdout_years))
    n_years = pd.Series([m for _, m in months]).value_counts()
    a = counts_in_months(dc, "AQUA", months)
    by_p4 = a.groupby(["p4", "month"])["n_focos"].sum()
    by_p4 = by_p4 / by_p4.index.get_level_values("month").map(n_years).to_numpy()
    reg = a.groupby("month")["n_focos"].sum() / n_years
    return by_p4, reg


# --------------------------------------------------------------------------------------
# Predicción en años reservados
# --------------------------------------------------------------------------------------
def _holdout_window(hp: HarmonizationParams) -> tuple[date, date]:
    return date(min(hp.holdout_years), 1, 1), date(max(hp.holdout_years), 12, 31)


def predict_cells(dc: DayCounts, cal: Calibration, src: str,
                  months: list[tuple[int, int]]) -> pd.DataFrame:
    """Aqua observado y predicho (cal x fuente) por celda-mes en ``months``."""
    keys = ["h3", "p4", "year", "month", "season"]
    obs = counts_in_months(dc, "AQUA", months).groupby(keys)["n_focos"].sum().rename("obs")
    raw = counts_in_months(dc, src, months).groupby(keys)["n_focos"].sum().rename("raw_value")
    cells = pd.concat([obs, raw], axis=1).fillna(0).reset_index()
    est, ratio = cal.ratio_for(cells["p4"], cells["season"])
    cells["estrato"], cells["pred"] = est.to_numpy(), ratio.to_numpy() * cells["raw_value"]
    return cells


def aggregate_units(cells: pd.DataFrame, group: list[str], cal: Calibration | None,
                    hp: HarmonizationParams) -> pd.DataFrame:
    """Suma celdas a unidades (celda padre-mes o región-mes) con banda del factor."""
    out = cells.groupby(group)[["obs", "pred", "raw_value"]].sum().reset_index()
    if cal is None:
        return out
    g = cells.groupby([*group, "estrato"])["raw_value"].sum().reset_index()
    band = factor_band(g, group, cal.boot, hp.band_quantiles)
    out = out.merge(band, on=group, how="left")
    return out.fillna({"factor_p10": 0.0, "factor_p90": 0.0})  # sin fuente: banda [0, 0]


def validate_chain(dc: DayCounts, cals: ProductionCalibrations, chain: str,
                   hp: HarmonizationParams) -> ChainValidation | None:
    src, pair = CHAINS[chain]
    if pair not in cals:
        log.warning("Validacion %s: el par %s no esta calibrado", chain, pair)
        return None
    cal = cals[pair]
    months = eligible_months(dc, ("AQUA", src), _holdout_window(hp), hp,
                             only_years=set(hp.holdout_years))
    if not months:
        log.warning("Validacion %s: sin meses reservados elegibles", chain)
        return None
    cells = predict_cells(dc, cal, src, months)
    act_p4, act_reg = expected_activity(dc, hp)
    r4 = aggregate_units(cells, ["p4", "year", "month"], cal, hp)
    reg = aggregate_units(cells, ["year", "month"], cal, hp)
    r4["activity"] = pd.Series(pd.MultiIndex.from_frame(r4[["p4", "month"]])
                               .map(act_p4.to_dict()), index=r4.index).fillna(0.0)
    reg["activity"] = reg["month"].map(act_reg).fillna(0.0)
    return ChainValidation(chain, pair, cal, cells, r4, reg)


# Error observado: satélite fuente del leave-one-year-out usado por cada cadena de validación.
# La cadena N20 usa el error de S-NPP: N20 y Aqua casi no se solapan fuera de 2019-2020.
LOYO_SOURCE = {"SNPP->AQUA": "SNPP", "N20->SNPP->AQUA": "SNPP", "TERRA->AQUA": "TERRA"}


def loyo_error_units(dc: DayCounts, src: str, hp: HarmonizationParams) -> pd.DataFrame:
    """Unidades (obs, pred) predichas fuera de muestra por leave-one-year-out.

    Ventana: la de calibración del par ``src -> AQUA``, SIN los años reservados. Para cada año Y
    se calibra con los demás años y se predice Y. Unidades: celda padre-mes y región-mes.
    """
    window = hp.calib_window if src == "SNPP" else hp.terra_aqua_window
    months = eligible_months(dc, ("AQUA", src), window, hp,
                             exclude_years=set(hp.holdout_years))
    parts = []
    for year in sorted({y for y, _ in months}):
        train = [ym for ym in months if ym[0] != year]
        test = [ym for ym in months if ym[0] == year]
        cal = calibrate_pair(dc, f"{src}->AQUA", "AQUA", src, train, hp,
                             np.random.default_rng(0), bootstrap=False)
        cells = predict_cells(dc, cal, src, test)
        for level, group in (("parent_r4", ["p4", "year", "month"]),
                             ("regional", ["year", "month"])):
            u = aggregate_units(cells, group, None, hp)
            parts.append(u[["obs", "pred"]].assign(level=level, loyo_year=year))
    return pd.concat(parts, ignore_index=True)


def error_models(dc: DayCounts, hp: HarmonizationParams) -> dict[str, tuple[pd.DataFrame, dict]]:
    """Modelo de error por satélite fuente (leave-one-year-out) + descripción."""
    out = {}
    for src in sorted(set(LOYO_SOURCE.values())):
        units = loyo_error_units(dc, src, hp)
        model = fit_error_model(units["obs"], units["pred"], hp)
        info = {"method": "leave-one-year-out sin anios reservados",
                "years": sorted(int(y) for y in units["loyo_year"].unique()),
                "n_units": {str(k): int(v) for k, v in units["level"].value_counts().items()}}
        out[src] = (model, info)
    return out


def contrast_regression(dc: DayCounts, hp: HarmonizationParams) -> dict:
    """log1p(Aqua) ~ log1p(SNPP) [+ log1p(px SNPP)], serie regional mensual, Duan smearing."""
    holdout = set(hp.holdout_years)
    train = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp, exclude_years=holdout)
    test = eligible_months(dc, ("AQUA", "SNPP"), _holdout_window(hp), hp, only_years=holdout)

    def regional(months):
        a = counts_in_months(dc, "AQUA", months).groupby(["year", "month"])["n_focos"].sum()
        s = counts_in_months(dc, "SNPP", months).groupby(["year", "month"])[
            ["n_focos", "n_px1km"]].sum()
        idx = pd.MultiIndex.from_tuples(months, names=["year", "month"])
        t = pd.DataFrame({"obs": a.reindex(idx, fill_value=0),
                          "v": s["n_focos"].reindex(idx, fill_value=0),
                          "px": s["n_px1km"].reindex(idx, fill_value=0)})
        return t.reset_index()

    tr, te = regional(train), regional(test)
    out = {}
    for name, cols in (("log1p_ols", ["v"]), ("log1p_ols_px", ["v", "px"])):
        x_tr = np.column_stack([np.ones(len(tr)), *[np.log1p(tr[c]) for c in cols]])
        y_tr = np.log1p(tr["obs"].to_numpy(float))
        coef, *_ = np.linalg.lstsq(x_tr, y_tr, rcond=None)
        smear = float(np.mean(np.exp(y_tr - x_tr @ coef)))
        x_te = np.column_stack([np.ones(len(te)), *[np.log1p(te[c]) for c in cols]])
        pred = np.exp(x_te @ coef) * smear - 1
        metrics = series_metrics(te.assign(pred=pred))
        out[name] = {"coef": [float(c) for c in coef], "duan_smearing": smear,
                     "n_train_months": len(tr), "regional": metrics}
    return out


def chain_report(v: ChainValidation, model: pd.DataFrame, model_info: dict,
                 hp: HarmonizationParams) -> dict:
    """Métricas de una cadena y cobertura FUERA DE MUESTRA de la banda en los años reservados."""
    r4, reg = v.units_r4, v.region
    cov_r4 = coverage(r4["obs"], r4["factor_p10"], r4["factor_p90"])
    cov_reg = coverage(reg["obs"], reg["factor_p10"], reg["factor_p90"])
    apply_widening = bool(cov_r4 < hp.band_min_coverage)
    use = model if apply_widening else None
    w4 = widen(r4["pred"], r4["factor_p10"], r4["factor_p90"], use, hp)
    wr = widen(reg["pred"], reg["factor_p10"], reg["factor_p90"], use, hp)
    cov_w = {"parent_r4_months": coverage(r4["obs"], *w4),
             "regional_months": coverage(reg["obs"], *wr)}
    lo, hi = hp.band_target_coverage
    return {
        "pair_applied": v.pair,
        "calibration_window": v.cal.window,
        "holdout_years": hp.holdout_years,
        "regional": series_metrics(reg),
        "by_parent_r4": by_unit_metrics(r4, hp.validation_min_focos_unit),
        "bias_by_activity_r4": bias_by_activity(r4),
        "bias_by_activity_regional": bias_by_activity(reg),
        "band": {
            "quantiles": list(hp.band_quantiles),
            "coverage_factor_only": {"parent_r4_months": cov_r4, "regional_months": cov_reg},
            "min_coverage": hp.band_min_coverage,
            "widened_with_observed_error": apply_widening,
            "coverage_out_of_sample": cov_w,
            "target_coverage": [lo, hi],
            "within_target": {k: bool(lo <= c <= hi) for k, c in cov_w.items()},
            "error_model": model.to_dict(orient="records"),
            "error_model_source": model_info,
            "n_units": {"parent_r4_months": int(len(r4)), "regional_months": int(len(reg))},
        },
    }


def holdout_validation(dc: DayCounts, hp: HarmonizationParams) -> dict:
    """Calibra sin los años reservados, estima el error por leave-one-year-out (también sin
    ellos) y valida todas las cadenas en los años reservados."""
    cals = fit_calibrations(dc, hp, exclude_years=set(hp.holdout_years))
    models = error_models(dc, hp)
    out = {}
    for chain in CHAINS:
        v = validate_chain(dc, cals, chain, hp)
        if v is None or LOYO_SOURCE[chain] not in models:
            continue
        model, info = models[LOYO_SOURCE[chain]]
        report = chain_report(v, model, {**info, "source_satellite": LOYO_SOURCE[chain]}, hp)
        out[chain] = {"report": report, "error_model": model, "validation": v}
    return out


def reliability_curve(v: ChainValidation, dc: DayCounts, hp: HarmonizationParams,
                      edges: list[float]) -> list[dict]:
    """Error relativo mensual (años reservados) de cada celda padre según su conteo anual
    esperado (suma de la actividad esperada de sus 12 meses). Justifica los umbrales de
    ``reliability`` en settings.yaml."""
    act_p4, _ = expected_activity(dc, hp)
    annual = act_p4.groupby(level="p4").sum()
    rows = []
    for p4, g in v.units_r4.groupby("p4"):
        rows.append({"annual": float(annual.get(p4, 0.0)), **series_metrics(g)})
    t = pd.DataFrame(rows).dropna(subset=["mae_rel"])
    bins = pd.cut(t["annual"], [*edges, np.inf], right=False)
    out = []
    for interval, g in t.groupby(bins, observed=True):
        out.append({"expected_annual": [float(interval.left), float(interval.right)],
                    "n_parent_cells": int(len(g)),
                    "mae_rel_median": float(g["mae_rel"].median()),
                    "mae_rel_p90": float(g["mae_rel"].quantile(0.9))})
    return out


def aqua_snpp_ratio_by_year(dc: DayCounts, hp: HarmonizationParams) -> dict:
    """Razón Aqua/S-NPP diurna por año (focos y píxeles ~1 km), meses completos de ambos."""
    window = (hp.satellite_periods["SNPP"][0], date(dc.last_month[0], 12, 31))
    months = eligible_months(dc, ("AQUA", "SNPP"), window, hp)
    out = {}
    for y in sorted({y for y, _ in months}):
        ms = [ym for ym in months if ym[0] == y]
        a = counts_in_months(dc, "AQUA", ms)[["n_focos", "n_px1km"]].sum()
        s = counts_in_months(dc, "SNPP", ms)[["n_focos", "n_px1km"]].sum()
        out[str(y)] = {"n_months": len(ms),
                       "focos": float(a["n_focos"] / s["n_focos"]) if s["n_focos"] else None,
                       "px1km": float(a["n_px1km"] / s["n_px1km"]) if s["n_px1km"] else None}
    return out


def synthetic_truth_check(dc: DayCounts, harmonized: pd.DataFrame, plan: pd.DataFrame,
                          truth: pd.DataFrame, hp: HarmonizationParams) -> dict:
    """Compara la serie armonizada con la verdad sin deriva de Aqua (escalada).

    k = sum(Aqua D limpio observado) / sum(verdad esperada sin deriva de Aqua D) en los meses de
    calibración; así la verdad queda en las mismas unidades (después de la limpieza).
    """
    t = truth[(truth["satellite"] == "AQUA") & (truth["daynight"] == "D")]
    t = t.groupby(["year", "month"])["expected_nodrift"].sum()
    calib = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp)
    aqua = dc.counts[dc.counts["satellite"] == "AQUA"].groupby(["year", "month"])[
        "n_focos"].sum()
    idx = pd.MultiIndex.from_tuples(calib, names=["year", "month"])
    k = float(aqua.reindex(idx, fill_value=0).sum() / t.reindex(idx, fill_value=0).sum())
    h = harmonized.groupby(["year", "month"])["value"].sum()
    after = plan[(plan["source"] == "viirs_converted") & ~plan["is_provisional"]]
    idx2 = pd.MultiIndex.from_frame(after[["year", "month"]])
    ref = k * t.reindex(idx2, fill_value=0)
    conv = h.reindex(idx2, fill_value=0)
    aq = aqua.reindex(idx2, fill_value=0)
    frame = lambda pred: pd.DataFrame({"year": idx2.get_level_values(0),  # noqa: E731
                                       "month": idx2.get_level_values(1),
                                       "obs": ref.to_numpy(), "pred": pred.to_numpy()})
    return {
        "description": "Verdad = esperado sin deriva de Aqua D x k (k ajusta por la limpieza).",
        "k": k,
        "months": f"{after['year'].min()}-{after['month'].iloc[0]:02d}.."
                  f"{after['year'].max()}-{after['month'].iloc[-1]:02d}",
        "viirs_converted_vs_truth": series_metrics(frame(conv)),
        "aqua_observed_vs_truth": series_metrics(frame(aq)),
    }


def make_plots(report_dir, dc: DayCounts, harmonized: pd.DataFrame, plan: pd.DataFrame,
               cals: ProductionCalibrations, validations: dict, ratio_by_year: dict) -> list[str]:
    """Gráficos de validación (PNG). Devuelve los nombres de archivo."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    files = []
    report_dir.mkdir(parents=True, exist_ok=True)
    c = dc.counts
    reg = c.groupby(["satellite", "year", "month"])["n_focos"].sum().unstack(0)
    reg.index = pd.to_datetime({"year": reg.index.get_level_values(0),
                                "month": reg.index.get_level_values(1), "day": 1})
    h = harmonized.groupby(["year", "month"])["value"].sum()
    h.index = pd.to_datetime({"year": h.index.get_level_values(0),
                              "month": h.index.get_level_values(1), "day": 1})
    snpp_conv = (c[c["satellite"] == "SNPP"].assign(
        r=lambda d: cals["SNPP->AQUA"].ratio_for(d["p4"], d["season"])[1] * d["n_focos"])
        .groupby(["year", "month"])["r"].sum())
    snpp_conv.index = pd.to_datetime({"year": snpp_conv.index.get_level_values(0),
                                      "month": snpp_conv.index.get_level_values(1), "day": 1})
    fig, ax = plt.subplots(figsize=(13, 5))
    since = pd.Timestamp("2012-01-01")
    ax.plot(reg.loc[since:, "AQUA"], label="Aqua D observado", lw=1.2)
    ax.plot(reg.loc[since:, "SNPP"], label="S-NPP D crudo", lw=0.8, alpha=0.6)
    ax.plot(snpp_conv.loc[since:], label="S-NPP D convertido", lw=1.0, ls="--")
    ax.plot(h.loc[since:], label="Serie armonizada", lw=1.0, color="k", alpha=0.7)
    ax.set_yscale("log")
    ax.set_title("Serie regional mensual, pasadas diurnas (sinteticos si data_mode=synthetic)")
    ax.set_ylabel("focos / mes")
    ax.legend()
    fig.tight_layout()
    fig.savefig(report_dir / "harmonization_series.png", dpi=110)
    plt.close(fig)
    files.append("harmonization_series.png")

    fig, axes = plt.subplots(1, len(validations), figsize=(5 * len(validations), 4.5))
    for ax, (chain, v) in zip(np.atleast_1d(axes), validations.items(), strict=True):
        u = v["validation"].units_r4
        u = u[(u["obs"] + u["pred"]) > 0]
        ax.scatter(u["pred"] + 1, u["obs"] + 1, s=6, alpha=0.4, label="celda padre-mes")
        r = v["validation"].region
        ax.scatter(r["pred"] + 1, r["obs"] + 1, s=18, color="k", label="region-mes")
        lim = [1, max(u["obs"].max(), u["pred"].max(), r["obs"].max()) + 2]
        ax.plot(lim, lim, color="gray", lw=0.8)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{chain} (anios reservados)")
        ax.set_xlabel("predicho + 1")
        ax.set_ylabel("Aqua observado + 1")
        ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(report_dir / "harmonization_scatter.png", dpi=110)
    plt.close(fig)
    files.append("harmonization_scatter.png")

    fig, ax = plt.subplots(figsize=(8, 4))
    years = [int(y) for y in ratio_by_year]
    ax.plot(years, [ratio_by_year[str(y)]["focos"] for y in years], marker="o", label="focos")
    ax.plot(years, [ratio_by_year[str(y)]["px1km"] for y in years], marker="s", label="px ~1 km")
    ax.set_title("Razon Aqua / S-NPP diurna por anio")
    ax.legend()
    fig.tight_layout()
    fig.savefig(report_dir / "aqua_snpp_ratio_by_year.png", dpi=110)
    plt.close(fig)
    files.append("aqua_snpp_ratio_by_year.png")
    return files
