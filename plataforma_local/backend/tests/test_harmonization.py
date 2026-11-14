"""Tests de la Fase 4: armonización (razón de sumas, estratos, bootstrap, banda, ensamblado)."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from firecal.etl.load import connect
from firecal.harmonization.band import coverage, factor_band, fit_error_model, widen
from firecal.harmonization.calibrate import calibrate_pair, compose
from firecal.harmonization.data import DayCounts, eligible_months, is_full_month, season_of


@pytest.fixture
def hp(settings):
    return settings.params.harmonization


def _dc(rows: list[tuple], hp, last=(2020, 12)) -> DayCounts:
    """rows: (h3, p4, p3, year, month, satellite, n_focos)."""
    df = pd.DataFrame(rows, columns=["h3", "p4", "p3", "year", "month", "satellite", "n_focos"])
    df["n_px1km"] = df["n_focos"]
    df["season"] = season_of(df["month"], hp.dry_season_months)
    prov = df[["satellite", "year", "month"]].drop_duplicates().assign(is_provisional=False)
    return DayCounts(df, prov, df[["h3", "p4", "p3"]].drop_duplicates(), last)


def _synthetic_pair(hp, ratios: dict[str, float], years=range(2013, 2019), src_per_month=100):
    """Celdas con razón Aqua/SNPP exacta por celda padre (meses secos y húmedos)."""
    rows = []
    for p4, r in ratios.items():
        for y in years:
            for m in range(1, 13):
                rows.append((f"c_{p4}", p4, "P3", y, m, "SNPP", src_per_month))
                rows.append((f"c_{p4}", p4, "P3", y, m, "AQUA", round(src_per_month * r)))
    return _dc(rows, hp)


def test_ratio_of_sums_and_bootstrap(hp):
    dc = _synthetic_pair(hp, {"A": 0.2, "B": 0.25})
    months = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp)
    cal = calibrate_pair(dc, "SNPP->AQUA", "AQUA", "SNPP", months, hp,
                         np.random.default_rng(0))
    est, ratio = cal.ratio_for(pd.Series(["A", "B"]), pd.Series(["seca", "seca"]))
    assert ratio.round(6).tolist() == [0.2, 0.25]
    assert est.str.startswith("r4:").all()
    s = cal.strata.set_index("estrato")
    assert ((s["p10"] <= s["ratio"] + 1e-12) & (s["ratio"] <= s["p90"] + 1e-12)).all()
    # razón constante en todos los años -> bootstrap sin dispersión
    assert np.allclose(s["p10"], s["ratio"]) and np.allclose(s["p90"], s["ratio"])


def test_small_strata_merge_to_mid_then_region(hp):
    # A tiene muchos focos; B y C pocos (ninguna alcanza 200 focos de Aqua por temporada).
    rows = []
    for y in range(2013, 2019):
        for m in range(1, 13):
            rows += [("a", "A", "P3x", y, m, "SNPP", 100), ("a", "A", "P3x", y, m, "AQUA", 20),
                     ("b", "B", "P3x", y, m, "SNPP", 5), ("b", "B", "P3x", y, m, "AQUA", 1),
                     ("c", "C", "P3y", y, m, "SNPP", 5), ("c", "C", "P3y", y, m, "AQUA", 1)]
    dc = _dc(rows, hp)
    months = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp)
    cal = calibrate_pair(dc, "SNPP->AQUA", "AQUA", "SNPP", months, hp,
                         np.random.default_rng(0))
    est, _ = cal.ratio_for(pd.Series(["A", "B", "C", "NUEVA"]), pd.Series(["seca"] * 4))
    assert est.iloc[0].startswith("r4:A")
    assert est.iloc[1].startswith("r3:P3x")      # B se fusiona con su padre res 3 (A + B)
    assert est.iloc[2] == "region|seca"          # C: su res 3 tampoco alcanza -> regional
    assert est.iloc[3] == "region|seca"          # celda nunca vista -> regional


def test_conversion_is_additive(hp):
    dc = _synthetic_pair(hp, {"A": 0.2, "B": 0.25})
    months = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp)
    cal = calibrate_pair(dc, "SNPP->AQUA", "AQUA", "SNPP", months, hp,
                         np.random.default_rng(0))
    v = pd.DataFrame({"p4": ["A", "A", "B"], "season": ["seca"] * 3, "raw": [3.0, 7.0, 4.0]})
    _, r = cal.ratio_for(v["p4"], v["season"])
    per_cell = (r * v["raw"]).sum()
    summed_first = 0.2 * 10.0 + 0.25 * 4.0
    assert per_cell == pytest.approx(summed_first)


def test_compose_multiplies_ratios_and_replicates(hp):
    dc = _synthetic_pair(hp, {"A": 0.2})
    m = eligible_months(dc, ("AQUA", "SNPP"), hp.calib_window, hp)
    inner = calibrate_pair(dc, "SNPP->AQUA", "AQUA", "SNPP", m, hp, np.random.default_rng(0))
    outer = calibrate_pair(dc, "SNPP->AQUA", "AQUA", "SNPP", m, hp, np.random.default_rng(1))
    comp = compose(outer, inner, "X->AQUA", hp)
    _, r = comp.ratio_for(pd.Series(["A"]), pd.Series(["humeda"]))
    assert r.iloc[0] == pytest.approx(0.04)
    any_est = comp.strata["estrato"].iloc[0]
    eo, ei = any_est.split(" * ")
    assert np.allclose(comp.boot[any_est], outer.boot[eo] * inner.boot[ei])


def test_factor_band_sums_replicates():
    boot = {"s1": np.array([1.0, 2.0, 3.0, 4.0, 5.0]), "s2": np.array([10.0] * 5)}
    g = pd.DataFrame({"m": [1, 1, 2], "estrato": ["s1", "s2", "s1"], "raw_value": [2.0, 1.0, 0.0]})
    out = factor_band(g, ["m"], boot, (0.0, 1.0)).set_index("m")
    assert out.loc[1, "factor_p10"] == pytest.approx(2 * 1 + 10)
    assert out.loc[1, "factor_p90"] == pytest.approx(2 * 5 + 10)
    assert out.loc[2, "factor_p10"] == out.loc[2, "factor_p90"] == 0


def test_error_model_depends_on_size(hp):
    """Error tipo Poisson: el error relativo debe achicarse con el conteo predicho."""
    rng = np.random.default_rng(0)
    pred = np.exp(rng.uniform(np.log(0.5), np.log(500), 20000))
    obs = rng.poisson(pred)
    model = fit_error_model(obs, pred, hp)
    assert model["pred_lo"].tolist() == hp.band_error_pred_edges
    width = (model["q_hi"] - model["q_lo"]).to_numpy()
    assert np.all(np.diff(width[1:]) < 0)          # más ancho para conteos chicos
    assert (model["q_lo"] <= 0).all() and (model["q_hi"] >= 0).all()
    lo, hi = widen(pred, pred, pred, model, hp)
    assert coverage(obs, pred, pred) < 0.2
    assert 0.7 <= coverage(obs, lo, hi) <= 0.9


def test_error_model_merges_small_bins(hp):
    pred = np.r_[np.full(500, 1.0), np.full(5, 50.0)]  # el rango [30, 120) tiene solo 5
    model = fit_error_model(pred, pred, hp)
    assert 30.0 not in model["pred_lo"].tolist() and model["n"].min() >= hp.band_error_min_n


def test_full_month_rule(hp):
    assert not is_full_month("SNPP", 2026, 11, hp)      # S-NPP termina el 1 de noviembre
    assert is_full_month("SNPP", 2026, 10, hp)
    assert not is_full_month("AQUA", 2002, 7, hp)       # Aqua empieza el 4 de julio
    assert is_full_month("AQUA", 2002, 8, hp)
    assert not is_full_month("N21", 2024, 1, hp)


# --------------------------------------------------------------------------------------
# Integración: pipeline sintético completo hasta la validación
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def harmonized_home(pipeline_home):
    return pipeline_home.settings, pipeline_home.summary, pipeline_home.metrics


def test_acceptance_holdout_bias(harmonized_home):
    """Aceptación: |sesgo relativo regional| < 15 % en los años reservados (SNPP -> AQUA)."""
    _, _, metrics = harmonized_home
    assert metrics["acceptance"]["passed"], metrics["acceptance"]
    n20 = metrics["chains"]["N20->SNPP->AQUA"]["regional"]["bias_rel"]
    assert abs(n20) < 0.15


def test_month_sources_and_tables(harmonized_home):
    settings, summary, _ = harmonized_home
    with connect(settings.paths.duckdb_path, read_only=True) as con:
        plan = con.execute("SELECT * FROM harmonized_months").df().set_index(["year", "month"])
        hm = con.execute("SELECT source, count(*) n, bool_and(value >= 0) ok, "
                         "bool_and(p10 <= value + 1e-9 AND value <= p90 + 1e-9) band_ok "
                         "FROM harmonized_monthly GROUP BY source").df().set_index("source")
        n_boot = con.execute("SELECT count(DISTINCT rep) FROM harmonization_bootstrap"
                             ).fetchall()[0][0]
    assert plan.loc[(2002, 7), "source"] == "terra_adjusted"
    assert bool(plan.loc[(2002, 7), "low_confidence"])
    assert plan.loc[(2002, 8), "source"] == "modis_observed"
    assert plan.loc[(2021, 6), "source"] == "modis_observed"
    assert plan.loc[(2021, 7), "satellite"] == "SNPP"
    assert plan.loc[(2026, 11), "satellite"] == "N20"   # S-NPP no cubre noviembre de 2026
    assert bool(plan.loc[(2026, 11), "is_provisional"])
    assert hm["ok"].all() and hm["band_ok"].all()
    assert n_boot == settings.params.harmonization.bootstrap_reps


def test_metrics_report_contents(harmonized_home):
    settings, _, metrics = harmonized_home
    path = settings.paths.reports_dir / "harmonization_metrics.json"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert "DIURNO" in on_disk["unit"]
    for chain in ("SNPP->AQUA", "N20->SNPP->AQUA", "TERRA->AQUA"):
        rep = on_disk["chains"][chain]
        assert rep["by_parent_r4"]["n_units"] > 0
        assert set(rep["bias_by_activity_r4"]) == {"bajo", "medio", "alto"}
        band = rep["band"]
        assert 0 <= band["coverage_factor_only"]["parent_r4_months"] <= 1
        assert set(band["coverage_out_of_sample"]) == {"parent_r4_months", "regional_months"}
        assert band["error_model_source"]["method"].startswith("leave-one-year-out")
        assert not set(band["error_model_source"]["years"]) & set(rep["holdout_years"])
    assert "log1p_ols" in on_disk["contrast_snpp_aqua"]
    assert on_disk["reliability_curve"]["curve"]
    truth = on_disk["synthetic_truth_check"]["viirs_converted_vs_truth"]
    assert abs(truth["bias_rel"]) < 0.15
    for name in on_disk["plots"]:
        assert (settings.paths.reports_dir / name).is_file()
