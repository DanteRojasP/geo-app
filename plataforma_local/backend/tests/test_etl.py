"""Tests de la Fase 2: loader, normalización y limpieza (sin red)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import box
from typer.testing import CliRunner

from firecal.cli import app as cli_app
from firecal.etl.archive_loader import detect_schema, load_archive
from firecal.etl.clean import bowtie_duplicates, clean_hotspots, drop_superseded_nrt
from firecal.etl.firms_schema import FIRMS_ASSUMPTIONS, classify_version
from firecal.etl.normalize import acq_time_minutes, modis_confidence_category
from firecal.etl.nrt_fetch import fetch_nrt
from firecal.grid.px1km import px1km_center, px1km_id
from firecal.regions import buffer_km, get_region
from firecal.synth.generator import generate

MODIS_HEADER = ("latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,"
                "confidence,version,bright_t31,frp,daynight,type")
VIIRS_NRT_HEADER = ("latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,"
                    "instrument,confidence,version,bright_ti5,frp,daynight")

MODIS_CSV = "\n".join([
    MODIS_HEADER,
    "-13.5,-72.0,320.1,1.0,1.0,2020-08-01,200,Aqua,MODIS,29,6.1,295.0,10.0,N,0",     # low
    "-13.5,-72.0,320.1,1.0,1.0,2020-08-01,0200,Terra,MODIS,30,6.1,295.0,10.0,N,0",   # nominal
    "-13.6,-72.1,320.1,1.0,1.0,2020-08-01,1830,Aqua,MODIS,80,6.1,295.0,10.0,D,2",    # high, type 2
    "-13.6,-72.1,320.1,1.0,1.0,2020-08-01,1830,X9,MODIS,80,6.1,295.0,10.0,D,0",      # desconocido
    "-13.6,-72.1,320.1,1.0,1.0,2020-08-01,2460,Aqua,MODIS,80,6.1,295.0,10.0,D,0",    # hora mala
]) + "\n"
VIIRS_NRT_CSV = "\n".join([
    VIIRS_NRT_HEADER,
    "-13.7,-72.2,330.0,0.4,0.4,2026-11-10,0644,N20,VIIRS,n,2.0NRT,290.0,3.1,N",
    "-13.7,-72.2,330.0,0.4,0.4,2026-11-10,1910,N21,VIIRS,h,2.0NRT,290.0,3.1,D",
]) + "\n"


@pytest.fixture
def firms_dir(tmp_path: Path) -> Path:
    d = tmp_path / "firms"
    d.mkdir()
    (d / "modis_sample.csv").write_text(MODIS_CSV, encoding="utf-8")
    (d / "viirs_nrt_sample.csv").write_text(VIIRS_NRT_CSV, encoding="utf-8")
    (d / "otra_cosa.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    return d


# --------------------------------------------------------------------------------------
# Esquema y normalización
# --------------------------------------------------------------------------------------
def test_detect_schema():
    assert detect_schema(MODIS_HEADER.split(",")) == "MODIS"
    assert detect_schema(VIIRS_NRT_HEADER.split(",")) == "VIIRS"
    assert detect_schema(["a", "b"]) is None
    no_time = [c for c in MODIS_HEADER.split(",") if c != "acq_time"]
    assert detect_schema(no_time) is None


def test_parse_acq_time_with_and_without_leading_zeros():
    raw = pd.Series(["552", "0552", "1830", "5", "552.0", "2460", "1261", "abc", "5.5", None])
    out = acq_time_minutes(raw)
    assert out.iloc[:5].tolist() == [352, 352, 1110, 5, 352]
    assert out.iloc[5:].isna().all()


def test_modis_confidence_bins():
    cat = modis_confidence_category(pd.Series(["0", "29", "30", "79", "80", "100"]), (30, 80))
    assert cat.tolist() == ["low", "low", "nominal", "nominal", "high", "high"]


@pytest.mark.parametrize(("raw", "expected"), [
    ("6.1", "SP"), ("61.03", "SP"), ("6.1NRT", "NRT"), ("2.0NRT", "NRT"),
    ("SYN", "SYN"), ("SYN-NRT", "SYN-NRT"),
])
def test_classify_version(raw, expected):
    assert classify_version(raw) == expected


def test_synthetic_satellite_codes_are_mapped(settings):
    """Los códigos que escribe el simulador deben estar en el mapeo único de supuestos."""
    codes = FIRMS_ASSUMPTIONS["satellite_codes"]
    for sat, cfg in settings.params.synthetic.satellites.items():
        assert codes[(cfg.sensor, cfg.code)] == sat


def test_load_archive_normalizes_both_schemas(settings, firms_dir, caplog):
    with caplog.at_level(logging.WARNING):
        df = load_archive(settings, input_dir=firms_dir)
    # 5 MODIS - 1 satélite desconocido - 1 hora inválida + 2 VIIRS
    assert len(df) == 5
    assert "X9" in caplog.text and "desconocido" in caplog.text
    assert "otra_cosa.csv" in caplog.text
    assert df["id"].tolist() == [1, 2, 3, 4, 5]

    modis = df[df["sensor"] == "MODIS"].set_index("satellite")
    # 02:00 UTC del 1 de agosto = 21:00 del 31 de julio en Lima
    assert modis.loc["AQUA"].iloc[0]["acq_utc"] == pd.Timestamp("2020-08-01 02:00")
    assert modis.loc["TERRA", "local_date"] == pd.Timestamp("2020-07-31")
    assert set(modis["confidence_cat"]) == {"low", "nominal", "high"}
    assert set(modis["version"]) == {"SP"}

    viirs = df[df["sensor"] == "VIIRS"]
    assert set(viirs["satellite"]) == {"N20", "N21"}
    assert viirs["type"].isna().all()  # el NRT no trae `type`
    assert set(viirs["version"]) == {"NRT"}
    assert viirs["confidence_cat"].tolist() == ["nominal", "high"]


def test_load_archive_missing_dir_gives_clear_error(settings, tmp_path):
    with pytest.raises(FileNotFoundError, match="firecal synth"):
        load_archive(settings, input_dir=tmp_path / "no_existe")


# --------------------------------------------------------------------------------------
# Limpieza
# --------------------------------------------------------------------------------------
def _frame(rows: list[dict]) -> pd.DataFrame:
    base = {"sensor": "MODIS", "satellite": "AQUA", "acq_utc": pd.Timestamp("2020-08-01 18:30"),
            "local_date": pd.Timestamp("2020-08-01"), "lat": -13.5, "lon": -72.0,
            "confidence_cat": "nominal", "confidence_raw": "50", "frp": 10.0, "daynight": "D",
            "type": 0, "version": "SP", "source_file": "x.csv"}
    df = pd.DataFrame([{**base, **r} for r in rows])
    df.insert(0, "id", range(1, len(df) + 1))
    df["type"] = df["type"].astype("Int64")
    return df


def test_bowtie_keeps_best_within_1km():
    km = 1 / 111.32
    df = _frame([
        {"confidence_raw": "60"},                                 # 1: mejor del par
        {"lat": -13.5 + 0.5 * km, "confidence_raw": "40"},        # 2: duplicado a 0.5 km
        {"lat": -13.5 + 1.5 * km},                                # 3: a 1.5 km -> se queda
        {"lat": -13.5 + 0.3 * km, "acq_utc": pd.Timestamp("2020-08-01 18:35")},  # otra pasada
        {"sensor": "VIIRS", "satellite": "N20", "lat": -13.5 + 0.2 * km},       # VIIRS: no aplica
    ])
    mask = bowtie_duplicates(df, max_km=1.0)
    assert df.loc[mask, "id"].tolist() == [2]


def test_sp_supersedes_nrt():
    df = _frame([
        {"version": "SP", "acq_utc": pd.Timestamp("2020-08-01 18:30")},
        {"version": "NRT", "acq_utc": pd.Timestamp("2020-08-01 06:30")},   # cubierto por SP
        {"version": "NRT", "acq_utc": pd.Timestamp("2020-08-02 06:30")},   # posterior: se queda
        {"version": "NRT", "satellite": "N21", "sensor": "VIIRS"},          # sin SP propio
    ])
    assert df.loc[drop_superseded_nrt(df), "id"].tolist() == [2]


def test_clean_region_buffer_static_type_and_confidence(settings):
    params = settings.params
    region = box(-72.5, -14.0, -71.5, -13.0)
    km_deg = 1 / 111.32
    rows = [
        {"lat": -13.5, "lon": -72.0},                                      # 1 dentro
        {"lat": -14.0 - 2 * km_deg, "lon": -72.0},                         # 2 a 2 km: buffer 3 km
        {"lat": -14.0 - 5 * km_deg, "lon": -72.0},                         # 3 a 5 km: fuera
        {"lat": -13.4, "lon": -71.8, "type": 2},                           # 4 fuente fija (SP)
        {"lat": -13.3, "lon": -71.9, "confidence_cat": "low"},             # 5 baja confianza
    ]
    # Una fuente fija detectada todos los meses de 2020 (también en NRT, sin type).
    for m in range(1, 13):
        ts = pd.Timestamp(f"2020-{m:02d}-15 18:30")
        rows.append({"lat": -13.2, "lon": -71.7, "type": 2, "acq_utc": ts,
                     "local_date": ts.normalize()})
        rows.append({"lat": -13.2, "lon": -71.7, "type": pd.NA, "version": "NRT",
                     "acq_utc": ts + pd.Timedelta(days=500), "satellite": "N20",
                     "sensor": "VIIRS", "local_date": (ts + pd.Timedelta(days=500)).normalize()})
    df = _frame(rows)
    clean, report = clean_hotspots(df, region, params)

    kept = set(clean["id"])
    assert {1, 2} <= kept and not {3, 4, 5} & kept
    assert report.removed["outside_region"] == {"AQUA": 1}
    assert report.removed["low_confidence"] == {"AQUA": 1}
    # todas las detecciones NRT de la fuente fija quedan marcadas (y fuera del cálculo)
    nrt = clean[clean["version"] == "NRT"]
    assert len(nrt) == 12 and nrt["is_static"].all()
    assert not clean.loc[clean["id"].isin([1, 2]), "is_static"].any()


def test_px1km_roundtrip():
    lat, lon = np.array([-13.5051, 0.0, 45.999]), np.array([-72.0049, 0.0, -179.995])
    ids = px1km_id(lat, lon, 0.01)
    clat, clon = px1km_center(ids, 0.01)
    assert np.all(np.abs(clat - lat) <= 0.005) and np.all(np.abs(clon - lon) <= 0.005)


def test_region_and_buffer(settings):
    region = get_region(settings)
    assert region.code == "peru_sur"
    grown = buffer_km(region.geometry, settings.params.region.buffer_km)
    w0, s0, _, _ = region.geometry.bounds
    w1, s1, _, _ = grown.bounds
    assert (s0 - s1) * 111.32 == pytest.approx(3.0, abs=0.1)
    assert w1 < w0


# --------------------------------------------------------------------------------------
# NRT pendiente, sin red
# --------------------------------------------------------------------------------------
def test_nrt_fetch_is_pending(settings):
    with pytest.raises(NotImplementedError, match="pendiente"):
        fetch_nrt(settings)


def test_cli_ingest_nrt_says_pending():
    result = CliRunner().invoke(cli_app, ["ingest", "--source", "nrt"])
    assert result.exit_code == 1


# --------------------------------------------------------------------------------------
# Integración con el simulador
# --------------------------------------------------------------------------------------
@pytest.fixture(scope="module")
def synthetic_clean(tmp_path_factory):
    from firecal.settings import EnvSettings, build_settings

    settings = build_settings(EnvSettings(_env_file=None))
    out = tmp_path_factory.mktemp("synthetic_etl")
    generate(settings, out_dir=out, scale=0.15, start=date(2016, 1, 1), end=date(2026, 11, 12))
    raw = load_archive(settings, input_dir=out)
    clean, report = clean_hotspots(raw, get_region(settings).geometry, settings.params)
    truth = pd.read_parquet(out / "truth.parquet")
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    return raw, clean, report, truth, manifest


def _near_sources(df: pd.DataFrame, manifest: dict, km: float = 2.5) -> np.ndarray:
    d = np.full(len(df), np.inf)
    for s in manifest["industrial_sources"]:
        dy = (df["lat"] - s["lat"]) * 111.32
        dx = (df["lon"] - s["lon"]) * 111.32 * np.cos(np.deg2rad(s["lat"]))
        d = np.minimum(d, np.hypot(dx, dy))
    return d < km


def test_synthetic_loads_everything(synthetic_clean):
    raw, _, _, truth, _ = synthetic_clean
    assert len(raw) == truth["n_total"].sum()


def test_synthetic_industrial_sources_excluded(synthetic_clean):
    """Aceptación: en modo sintético las fuentes industriales quedan excluidas."""
    _, clean, _, _, manifest = synthetic_clean
    assert not (clean["type"] == 2).any()  # SP: por `type`
    usable = clean[~clean["is_static"]]
    nrt_near = usable["version"].eq("SYN-NRT") & _near_sources(usable, manifest)
    all_nrt_near = clean["version"].eq("SYN-NRT") & _near_sources(clean, manifest)
    # NRT (sin `type`): por el filtro de fuentes fijas; tolera detecciones dispersas por
    # geolocalización que caen en celdas de ~1 km poco frecuentes.
    assert nrt_near.sum() <= 0.25 * all_nrt_near.sum()


def test_synthetic_bowtie_matches_truth(synthetic_clean):
    _, _, report, truth, _ = synthetic_clean
    removed = sum(report.removed["bowtie"].values())
    expected = truth.loc[truth["satellite"].isin(["TERRA", "AQUA"]), "n_bowtie"].sum()
    assert removed == pytest.approx(expected, rel=0.05)


def test_synthetic_static_does_not_eat_vegetation(synthetic_clean):
    _, clean, _, _, manifest = synthetic_clean
    far = ~_near_sources(clean, manifest, km=5)
    assert clean.loc[far, "is_static"].sum() == 0
