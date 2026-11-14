"""Tests de la Fase 5: climatología, anomalía y percentiles con series pequeñas conocidas."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from firecal.climatology.anomaly import anomaly, category, reliability
from firecal.climatology.aoi import HarmonizedData, aoi_series, raw_series, raw_viirs_series
from firecal.climatology.climatology import expected_annual, monthly_climatology
from firecal.climatology.percentiles import (
    harmonized_percentiles,
    percentile_rank,
    sensor_independent_percentiles,
)

CUTS = (10, 25, 75, 90)


def _series(values_by_year: dict[int, list[float]], provisional_last: bool = False):
    rows = []
    for y, vals in values_by_year.items():
        for m, v in enumerate(vals, start=1):
            rows.append({"year": y, "month": m, "value": float(v), "provisional": False})
    df = pd.DataFrame(rows)
    if provisional_last:
        df.loc[df.index[-1], "provisional"] = True
    return df


def test_percentile_rank_midrank():
    assert percentile_rank(5, [1, 2, 3, 4]) == 100.0
    assert percentile_rank(0, [1, 2, 3, 4]) == 0.0
    assert percentile_rank(2, [1, 2, 3, 4]) == pytest.approx(37.5)  # 1 abajo + 0.5 empate
    assert percentile_rank(3, []) is None


def test_monthly_climatology_known_values():
    # 4 años; agosto = 10, 20, 30, 40 -> mediana 25, p25 17.5, p75 32.5, p90 37
    s = _series({2003 + i: [1] * 7 + [10 * (i + 1)] + [1] * 4 for i in range(4)})
    clim = monthly_climatology(s, (2003, 2006)).set_index("month")
    assert clim.loc[8, "median"] == 25
    assert clim.loc[8, "p25"] == pytest.approx(17.5)
    assert clim.loc[8, "p75"] == pytest.approx(32.5)
    assert clim.loc[8, "p90"] == pytest.approx(37.0)
    assert clim.loc[1, "median"] == 1 and clim.loc[1, "n_years"] == 4


def test_climatology_respects_base_years_and_provisional():
    s = _series({2001: [100] * 12, 2003: [1] * 12, 2004: [3] * 12, 2005: [1000] * 12},
                provisional_last=True)
    clim = monthly_climatology(s, (2003, 2005)).set_index("month")
    assert clim.loc[1, "median"] == 3          # 2001 fuera de la base; 1, 3, 1000
    assert clim.loc[12, "n_years"] == 2        # dic-2005 provisional: fuera


def test_expected_annual_only_full_years():
    s = _series({2003: [1] * 12, 2004: [2] * 12, 2005: [5] * 6})
    assert expected_annual(s, (2003, 2005)) == pytest.approx((12 + 24) / 2)


def test_anomaly_known_values():
    s = _series({2003: [0] * 7 + [10] + [0] * 4, 2004: [0] * 7 + [20] + [0] * 4,
                 2005: [0] * 7 + [30] + [0] * 4, 2026: [0] * 7 + [60] + [0] * 4})
    a = anomaly(s, 2026, 8, (2003, 2022), CUTS)
    assert a["median"] == 20 and a["value"] == 60
    assert a["anomaly_abs"] == 40 and a["anomaly_pct"] == pytest.approx(200.0)
    assert a["percentile"] == 100.0 and a["category"] == "muy por encima"
    with pytest.raises(KeyError):
        anomaly(s, 2030, 1, (2003, 2022), CUTS)


def test_category_cuts():
    assert [category(p, CUTS) for p in (5, 20, 50, 80, 95)] == [
        "muy por debajo", "por debajo", "normal", "por encima", "muy por encima"]


def test_reliability_thresholds(settings):
    r = settings.params.reliability
    assert reliability(None, r) == "baja"
    assert reliability(r.expected_annual_low - 1, r) == "baja"
    assert reliability(r.expected_annual_low, r) == "media"
    assert reliability(r.expected_annual_high, r) == "alta"


def test_harmonized_percentiles():
    s = _series({2003: [1] * 12, 2004: [2] * 12, 2005: [3] * 12, 2006: [4] * 12})
    p = harmonized_percentiles(s, (2003, 2006))
    assert p.iloc[0] == pytest.approx(12.5) and p.iloc[-1] == pytest.approx(87.5)


# --------------------------------------------------------------------------------------
# Series de un AOI a partir de tablas armonizadas pequeñas
# --------------------------------------------------------------------------------------
@pytest.fixture
def tiny(settings) -> HarmonizedData:
    hp = settings.params.harmonization
    months = pd.DataFrame([
        {"year": 2010, "month": 8, "source": "modis_observed", "satellite": "AQUA", "pair": None,
         "low_confidence": False, "is_provisional": False},
        {"year": 2011, "month": 8, "source": "modis_observed", "satellite": "AQUA", "pair": None,
         "low_confidence": False, "is_provisional": False},
        {"year": 2022, "month": 8, "source": "viirs_converted", "satellite": "SNPP",
         "pair": "SNPP->AQUA", "low_confidence": False, "is_provisional": False},
        {"year": 2026, "month": 11, "source": "viirs_converted", "satellite": "N20",
         "pair": "N20->AQUA", "low_confidence": False, "is_provisional": True},
    ])
    harmonized = pd.DataFrame([
        {"h3": "a", "year": 2010, "month": 8, "value": 4.0, "raw_value": 4.0, "pair": None,
         "estrato": None},
        {"h3": "b", "year": 2010, "month": 8, "value": 6.0, "raw_value": 6.0, "pair": None,
         "estrato": None},
        {"h3": "a", "year": 2022, "month": 8, "value": 10.0, "raw_value": 50.0,
         "pair": "SNPP->AQUA", "estrato": "s1"},
        {"h3": "b", "year": 2022, "month": 8, "value": 20.0, "raw_value": 80.0,
         "pair": "SNPP->AQUA", "estrato": "s2"},
    ])
    raw = pd.DataFrame([
        {"h3": "a", "year": 2010, "month": 8, "satellite": "AQUA", "n_focos": 4},
        {"h3": "a", "year": 2022, "month": 8, "satellite": "SNPP", "n_focos": 50},
        {"h3": "a", "year": 2022, "month": 8, "satellite": "N20", "n_focos": 55},
        {"h3": "a", "year": 2026, "month": 11, "satellite": "N20", "n_focos": 7},
    ])
    boot = {"SNPP->AQUA": {"s1": np.full(10, 0.2), "s2": np.linspace(0.2, 0.3, 10)}}
    return HarmonizedData(harmonized, months, raw, boot, {}, hp)


def test_aoi_series_sums_cells_and_fills_zeros(tiny):
    s = aoi_series(tiny, {"a", "b"}).set_index(["year", "month"])
    assert s.loc[(2010, 8), "value"] == 10
    assert s.loc[(2010, 8), "band_p10"] == s.loc[(2010, 8), "band_p90"] == 10  # observado
    assert s.loc[(2011, 8), "value"] == 0                                       # sin focos
    assert s.loc[(2022, 8), "value"] == 30
    # banda del factor: sum_s R_s^b V_s, p10/p90 de 50*0.2 + 80*[0.2..0.3]
    totals = 50 * 0.2 + 80 * np.linspace(0.2, 0.3, 10)
    assert s.loc[(2022, 8), "band_p10"] == pytest.approx(np.quantile(totals, 0.1))
    assert s.loc[(2022, 8), "band_p90"] == pytest.approx(np.quantile(totals, 0.9))
    assert bool(s.loc[(2026, 11), "provisional"])
    only_a = aoi_series(tiny, {"a"}).set_index(["year", "month"])
    assert only_a.loc[(2010, 8), "value"] == 4 and only_a.loc[(2022, 8), "value"] == 10


def test_raw_series_and_viirs_never_summed(tiny):
    aqua = raw_series(tiny, {"a"}, "AQUA").set_index(["year", "month"])["value"]
    assert aqua.loc[(2010, 8)] == 4 and aqua.loc[(2011, 8)] == 0
    viirs = raw_viirs_series(tiny, {"a"}).set_index(["year", "month"])
    assert viirs.loc[(2022, 8), "value"] == 50          # S-NPP, no S-NPP + N20
    assert viirs.loc[(2022, 8), "satellite"] == "SNPP"
    assert viirs.loc[(2026, 11), "satellite"] == "N20"  # S-NPP no cubre nov-2026


def test_sensor_independent_percentiles(tiny):
    p = sensor_independent_percentiles(tiny, {"a"}, (2003, 2022), min_years=1)
    p = p.set_index(["year", "month"])
    # Aqua agosto: muestra {4 (2010), 0 (2011)} -> 2010 = 75, 2011 = 25
    assert p.loc[(2010, 8), "percentile"] == pytest.approx(75.0)
    assert p.loc[(2011, 8), "percentile"] == pytest.approx(25.0)
    assert p.loc[(2010, 8), "satellite"] == "AQUA"
