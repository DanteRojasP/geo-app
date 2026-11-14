"""Tests de la Fase 3: agregación mensual."""

from __future__ import annotations

import shutil
from datetime import date

import duckdb
import pandas as pd
import pytest

from firecal.etl.aggregate import assign_h3, build_monthly_counts
from firecal.etl.load import HOTSPOT_TYPES, connect, write_table
from firecal.etl.normalize import normalize_frame
from firecal.pipeline import run_aggregate, run_clean, run_ingest
from firecal.settings import PROJECT_ROOT, Paths, Settings
from firecal.synth.generator import generate


def _hotspots_db(rows: list[dict]) -> duckdb.DuckDBPyConnection:
    base = {"sensor": "MODIS", "satellite": "AQUA", "acq_utc": pd.Timestamp("2020-08-10 18:30"),
            "local_date": pd.Timestamp("2020-08-10"), "lat": -13.5, "lon": -72.0,
            "confidence_cat": "nominal", "confidence_raw": "50", "frp": 1.0, "daynight": "D",
            "type": 0, "version": "SP", "source_file": "x", "h3_7": None, "px1km_id": 1,
            "is_static": False}
    df = pd.DataFrame([{**base, **r} for r in rows])
    df.insert(0, "id", range(1, len(df) + 1))
    con = duckdb.connect(":memory:")
    write_table(con, "hotspots", df[list(HOTSPOT_TYPES)], HOTSPOT_TYPES)
    con.execute("CREATE VIEW hotspots_clean AS SELECT * FROM hotspots WHERE NOT is_static")
    return con


def test_month_border_uses_local_time():
    """Aceptación: un foco a las 02:00 UTC del día 1 cae en el mes anterior (hora de Lima)."""
    raw = pd.DataFrame({
        "latitude": ["-13.5"], "longitude": ["-72.0"], "acq_date": ["2020-09-01"],
        "acq_time": ["200"], "satellite": ["Aqua"], "confidence": ["50"], "version": ["6.1"],
        "frp": ["5.0"], "daynight": ["N"], "type": ["0"],
    })
    norm = normalize_frame(raw, "MODIS", "borde.csv", timezone="America/Lima",
                           modis_bins=(30, 80))
    assert norm.loc[0, "local_date"] == pd.Timestamp("2020-08-31")
    con = _hotspots_db([{"acq_utc": norm.loc[0, "acq_utc"], "local_date": norm.loc[0, "local_date"],
                         "daynight": "N"}])
    assign_h3(con, 7)
    build_monthly_counts(con)
    year, month = con.execute("SELECT year, month FROM monthly_counts").fetchone()
    assert (year, month) == (2020, 8)


def test_counts_px1km_static_and_provisional():
    con = _hotspots_db([
        {"px1km_id": 10},                                           # mismo píxel ...
        {"px1km_id": 10, "lat": -13.5001},                          # ... 2 focos, 1 píxel
        {"px1km_id": 11, "lat": -13.505},                           # otro píxel
        {"px1km_id": 12, "is_static": True},                        # fuente fija: excluida
        {"daynight": "N", "px1km_id": 10},                          # noche: otra fila
        {"satellite": "N20", "sensor": "VIIRS", "version": "NRT",   # NRT -> provisional
         "px1km_id": 10},
    ])
    assign_h3(con, 7)
    build_monthly_counts(con)
    mc = con.execute("SELECT satellite, daynight, sum(n_focos) f, sum(n_px1km) p, "
                     "bool_or(is_provisional) prov FROM monthly_counts GROUP BY ALL "
                     "ORDER BY ALL").df()
    rows = {(r.satellite, r.daynight): (r.f, r.p, r.prov) for r in mc.itertuples()}
    assert rows[("AQUA", "D")] == (3, 2, False)
    assert rows[("AQUA", "N")] == (1, 1, False)
    assert rows[("N20", "D")] == (1, 1, True)
    total = con.execute("SELECT sum(n_focos) FROM monthly_counts").fetchone()[0]
    clean = con.execute("SELECT count(*) FROM hotspots_clean").fetchone()[0]
    assert total == clean == 5


@pytest.fixture(scope="module")
def pipeline_db(tmp_path_factory):
    """Pipeline sintético completo (synth, ingest, clean, aggregate) en una carpeta aislada."""
    from firecal.settings import EnvSettings, load_params

    home = tmp_path_factory.mktemp("home")
    shutil.copytree(PROJECT_ROOT / "config", home / "config")
    settings = Settings(env=EnvSettings(_env_file=None),
                        params=load_params(home / "config" / "settings.yaml"),
                        paths=Paths(home=home))
    generate(settings, scale=0.1, start=date(2017, 1, 1), end=date(2026, 11, 12))
    run_ingest(settings)
    run_clean(settings)
    out = run_aggregate(settings)
    return settings, out


def test_pipeline_sum_matches_clean_hotspots(pipeline_db):
    """Aceptación: la suma de n_focos coincide con el conteo de hotspots limpios."""
    settings, out = pipeline_db
    with connect(settings.paths.duckdb_path, read_only=True) as con:
        n_clean = con.execute("SELECT count(*) FROM hotspots_clean").fetchone()[0]
        n_null_h3 = con.execute("SELECT count(*) FROM hotspots WHERE h3_7 IS NULL").fetchone()[0]
    assert out["n_focos"] == n_clean
    assert n_null_h3 == 0


def test_pipeline_cells_and_coverage(pipeline_db):
    settings, _ = pipeline_db
    with connect(settings.paths.duckdb_path, read_only=True) as con:
        cov = con.execute("SELECT * FROM satellite_coverage").df().set_index("satellite")
        orphan = con.execute("SELECT count(*) FROM monthly_counts m "
                             "ANTI JOIN cells c ON m.h3 = c.h3").fetchone()[0]
        in_region = con.execute("SELECT count(*) FROM cells "
                                "WHERE list_contains(region_codes, 'peru_sur')").fetchone()[0]
        parents_ok = con.execute("SELECT bool_and(length(parent_calib) = 15) FROM cells"
                                 ).fetchone()[0]
    assert orphan == 0
    assert in_region > 20000 and parents_ok
    assert cov.loc["N21", "first_yyyymm"] == 202401
    assert cov.loc["SNPP", "last_yyyymm"] == 202611
    assert cov.loc["AQUA", "nrt_from_yyyymm"] == 202607
