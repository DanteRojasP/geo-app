"""Tests de la Fase 1: simulador de focos con formato FIRMS.

Se genera una vez (escala reducida, periodo completo, fecha final fija) en una carpeta
temporal y se verifican esquema, ratio VIIRS/Aqua, estacionalidad, periodos activos y verdad.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from firecal.settings import EnvSettings, build_settings
from firecal.synth.generator import MODIS_COLUMNS, VIIRS_COLUMNS, generate

TEST_SCALE = 0.2
TEST_END = date(2026, 11, 12)


@pytest.fixture(scope="session")
def synth_run(tmp_path_factory):
    settings = build_settings(EnvSettings(_env_file=None))
    out = tmp_path_factory.mktemp("synthetic")
    result = generate(settings, out_dir=out, scale=TEST_SCALE, end=TEST_END)
    return settings, result


@pytest.fixture(scope="session")
def hotspots(synth_run) -> pd.DataFrame:
    """Todos los CSV en un DataFrame, con fecha local calculada a partir de la hora UTC."""
    settings, result = synth_run
    frames = []
    for path in sorted(result.out_dir.glob("*.csv")):
        df = pd.read_csv(path, dtype={"acq_time": str, "confidence": str})
        df["_file"] = path.name
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    utc = pd.to_datetime(df["acq_date"] + df["acq_time"], format="%Y-%m-%d%H%M", utc=True)
    df["local_date"] = utc.dt.tz_convert(settings.params.timezone).dt.date
    code_to_sat = {v.code: k for k, v in settings.params.synthetic.satellites.items()}
    df["sat"] = df["satellite"].map(code_to_sat)
    return df


def test_schema_matches_firms(synth_run):
    _, result = synth_run
    for path in result.out_dir.glob("*.csv"):
        header = path.read_text(encoding="utf-8").splitlines()[0].split(",")
        expected = MODIS_COLUMNS if path.name.startswith("modis") else VIIRS_COLUMNS
        if path.name.endswith("_syn-nrt.csv"):
            expected = [c for c in expected if c != "type"]  # NRT de FIRMS no trae `type`
        assert header == expected, path.name


def test_value_domains(hotspots):
    modis = hotspots[hotspots["instrument"] == "MODIS"]
    viirs = hotspots[hotspots["instrument"] == "VIIRS"]
    conf = modis["confidence"].astype(int)
    assert conf.between(0, 100).all()
    assert set(viirs["confidence"]) <= {"l", "n", "h"}
    assert set(hotspots["daynight"]) == {"D", "N"}
    assert set(hotspots["version"]) == {"SYN", "SYN-NRT"}
    assert hotspots["acq_time"].str.fullmatch(r"\d{4}").all()
    sp = hotspots[hotspots["version"] == "SYN"]
    assert set(sp["type"].astype(int)) == {0, 2}


def test_viirs_aqua_day_ratio_in_range(synth_run):
    """Aceptación: VIIRS/Aqua diurno entre 3 y 7 (sobre los periodos comunes, sin deriva)."""
    settings, result = synth_run
    truth = pd.read_parquet(result.out_dir / "truth.parquet")
    day = truth[truth["daynight"] == "D"]
    drift_nodes = settings.params.synthetic.overpass_drift.values()
    drift_year = min(nodes[0][0].year for nodes in drift_nodes)
    piv = day.pivot_table(index=["year", "month"], columns="satellite", values="n_total",
                          aggfunc="sum")
    for viirs in ("SNPP", "N20"):
        common = piv[[viirs, "AQUA"]].dropna()
        common = common[common.index.get_level_values("year") < drift_year]
        ratio = common[viirs].sum() / common["AQUA"].sum()
        assert 3 <= ratio <= 7, f"{viirs}/AQUA = {ratio:.2f}"


def test_seasonal_peak_aug_oct(hotspots):
    """Aceptación: pico estacional en ago-oct y mínimo en dic-mar (por satélite)."""
    month = pd.to_datetime(hotspots["local_date"]).dt.month
    for sat, grp in hotspots[hotspots["daynight"] == "D"].groupby("sat"):
        by_month = grp.groupby(month.loc[grp.index]).size().reindex(range(1, 13), fill_value=0)
        assert by_month.idxmax() in (8, 9, 10), sat
        assert by_month.idxmin() in (12, 1, 2, 3), sat


def test_active_periods_respected(synth_run, hotspots):
    """Aceptación: ningún satélite tiene focos fuera de su periodo activo (fecha local)."""
    settings, _ = synth_run
    sats = settings.params.synthetic.satellites
    for sat, grp in hotspots.groupby("sat"):
        cfg = sats[sat]
        last = cfg.end or TEST_END
        assert grp["local_date"].min() >= cfg.start, sat
        assert grp["local_date"].max() <= last, sat
        # y efectivamente opera hasta cerca del final de su periodo
        assert grp["local_date"].max() >= last - timedelta(days=31), sat
    assert set(hotspots["sat"]) == set(sats)
    assert hotspots.loc[hotspots["sat"] == "SNPP", "local_date"].max() <= date(2026, 11, 1)


def test_nrt_only_at_the_end(synth_run, hotspots):
    settings, _ = synth_run
    nrt_start = TEST_END - timedelta(days=settings.params.synthetic.nrt_days - 1)
    is_nrt = hotspots["version"] == "SYN-NRT"
    assert (hotspots.loc[is_nrt, "local_date"] >= nrt_start).all()
    assert (hotspots.loc[~is_nrt, "local_date"] < nrt_start).all()
    assert hotspots.loc[is_nrt, "type"].isna().all()


def test_industrial_sources_almost_every_month(synth_run, hotspots):
    """Las fuentes fijas (type=2) aparecen en casi todos los meses: la Fase 2 debe excluirlas."""
    settings, _ = synth_run
    ind = hotspots[(hotspots["type"] == 2) & (hotspots["sat"] == "AQUA")]
    months_with = pd.to_datetime(ind["local_date"]).dt.to_period("M").nunique()
    aqua = settings.params.synthetic.satellites["AQUA"].start
    total_months = (TEST_END.year - aqua.year) * 12 + TEST_END.month - aqua.month + 1
    nrt_months = settings.params.synthetic.nrt_days / 30  # en NRT no hay `type`
    assert months_with / (total_months - nrt_months) > 0.9


def test_truth_matches_csv(synth_run, hotspots):
    """La verdad cuenta exactamente las filas escritas, y el esperado se parece al realizado."""
    settings, result = synth_run
    truth = pd.read_parquet(result.out_dir / "truth.parquet")
    by_sat = truth.groupby("satellite")["n_total"].sum()
    assert by_sat.to_dict() == hotspots.groupby("sat").size().to_dict()
    veg = truth.groupby("satellite")[["expected", "n_vegetation"]].sum()
    rel = (veg["n_vegetation"] / veg["expected"] - 1).abs()
    assert (rel < 0.05).all(), rel
    # sin deriva (satélites sin nodos, o antes del primer nodo) esperado == esperado sin deriva
    drift = settings.params.synthetic.overpass_drift
    month_start = pd.to_datetime(dict(year=truth["year"], month=truth["month"], day=1)).dt.date
    first_node = truth["satellite"].map({k: v[0][0] for k, v in drift.items()})
    no_drift = first_node.isna() | (month_start.map(lambda d: d.replace(day=28)) < first_node)
    exp, exp0 = truth["expected"], truth["expected_nodrift"]
    assert np.allclose(exp[no_drift], exp0[no_drift])
    assert not np.allclose(exp[~no_drift], exp0[~no_drift])
    events = pd.read_parquet(result.out_dir / "truth_events.parquet")
    assert len(events) == result.n_events


def test_manifest(synth_run):
    _, result = synth_run
    manifest = json.loads((result.out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_mode"] == "synthetic"
    assert manifest["total_rows"] == result.total_rows
    assert manifest["files"] == result.rows_per_file
    assert manifest["end"] == TEST_END.isoformat()


def test_deterministic_and_independent_streams(tmp_path: Path):
    """Misma semilla -> mismos archivos. Cambiar la detección no cambia los eventos."""
    settings = build_settings(EnvSettings(_env_file=None))
    kw = {"scale": 0.1, "start": date(2015, 1, 1), "end": date(2015, 12, 31)}
    a = generate(settings, out_dir=tmp_path / "a", **kw)
    b = generate(settings, out_dir=tmp_path / "b", **kw)
    assert a.rows_per_file == b.rows_per_file
    for name in a.rows_per_file:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()

    raw = settings.params.model_dump()
    raw["synthetic"]["sensors"]["MODIS"]["s50_ha"] *= 2
    other = settings.model_copy(update={"params": type(settings.params).model_validate(raw)})
    c = generate(other, out_dir=tmp_path / "c", **kw)
    ev_a = pd.read_parquet(tmp_path / "a" / "truth_events.parquet")
    ev_c = pd.read_parquet(tmp_path / "c" / "truth_events.parquet")
    pd.testing.assert_frame_equal(ev_a, ev_c)
    assert c.rows_per_file != a.rows_per_file
    assert np.isfinite(c.total_rows)
