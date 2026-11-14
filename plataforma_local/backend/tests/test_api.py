"""Tests de la Fase 6: API completa en modo sintético (TestClient, sin red)."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from firecal.settings import EnvSettings, Paths, Settings

REG = {"type": "region", "code": "peru_sur"}
BBOX_A = [-72.6, -13.8, -72.2, -13.2]
BBOX_B = [-72.2, -13.8, -71.8, -13.2]
BBOX_AB = [-72.6, -13.8, -71.8, -13.2]
ENVELOPE = {"data_mode", "data_version", "generated_at", "notes"}


@pytest.fixture(scope="module")
def api(pipeline_home) -> TestClient:
    return TestClient(create_app(pipeline_home.settings))


def _ok(resp):
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) >= ENVELOPE
    assert body["data_mode"] == "synthetic"
    assert any("sintéticos" in n for n in body["notes"])
    return body


def test_health_ready(api):
    assert api.get("/health").json() == {"status": "ok", "data_mode": "synthetic",
                                         "data_ready": True}


def test_regions(api):
    body = _ok(api.get("/api/v1/regions"))
    by_code = {f["properties"]["code"]: f for f in body["features"]}
    assert {"peru_sur", "PE-CUS", "PE-PUN"} <= set(by_code)
    feat = by_code["PE-CUS"]
    assert feat["properties"]["level"] == "departamento"
    assert feat["geometry"]["type"] in ("Polygon", "MultiPolygon")
    assert feat["properties"]["n_cells"] > 0


def test_calendar_region_default(api, pipeline_home):
    body = _ok(api.post("/api/v1/calendar", json={"aoi": REG}))
    assert body["mode"] == "harmonized" and "diurno" in body["unit"]
    assert body["years"][0] == 2003 and body["months"] == list(range(1, 13))
    assert len(body["climatology"]) == 12
    assert body["reliability"] == "alta" and body["expected_annual"] > 100
    assert body["aoi"]["type"] == "region" and body["aoi"]["n_cells"] > 20000
    cell = body["cells"][0]
    assert {"year", "month", "value", "band_p10", "band_p90", "percentile", "source",
            "provisional"} <= set(cell)
    conv = [c for c in body["cells"] if c["source"] == "viirs_converted"]
    assert all(c["band_p10"] <= c["band_p90"] for c in conv)
    inside = sum(c["band_p10"] <= c["value"] <= c["band_p90"] for c in conv)
    assert inside / len(conv) > 0.95
    obs = [c for c in body["cells"] if c["source"] == "modis_observed"]
    assert all(c["band_p10"] == c["value"] == c["band_p90"] for c in obs)
    assert any(c["provisional"] for c in body["cells"])
    assert any("provisionales" in n for n in body["notes"])
    assert any("diurnas" in n for n in body["notes"])


def test_calendar_early_years_low_confidence(api):
    body = _ok(api.post("/api/v1/calendar", json={"aoi": REG, "start_year": 2000,
                                                  "end_year": 2003}))
    early = {(c["year"], c["month"]): c for c in body["cells"]}
    assert early[(2002, 7)]["source"] == "terra_adjusted" and early[(2002, 7)]["low_confidence"]
    assert any("baja confianza" in n for n in body["notes"])


@pytest.mark.parametrize("mode", ["percentile", "raw_modis", "raw_viirs"])
def test_calendar_other_modes(api, mode):
    body = _ok(api.post("/api/v1/calendar", json={"aoi": {"type": "bbox", "bbox": BBOX_AB},
                                                  "mode": mode}))
    assert body["mode"] == mode and body["cells"]
    if mode == "percentile":
        vals = [c["value"] for c in body["cells"] if c["value"] is not None]
        assert vals and all(0 <= v <= 100 for v in vals)
    if mode == "raw_viirs":
        assert {c["satellite"] for c in body["cells"]} <= {"SNPP", "N20", "N21"}
        assert all(c["source"].endswith("_raw") for c in body["cells"])
    if mode == "raw_modis":
        assert {c["satellite"] for c in body["cells"]} == {"AQUA"}


def test_calendar_is_additive(api):
    """Calendario de A ∪ B = A + B (razón de sumas aditiva; mismas celdas H3)."""
    def values(bbox):
        body = api.post("/api/v1/calendar", json={"aoi": {"type": "bbox", "bbox": bbox}}).json()
        return {(c["year"], c["month"]): c["value"] for c in body["cells"]}, body["aoi"]

    a, ia = values(BBOX_A)
    b, ib = values(BBOX_B)
    ab, iab = values(BBOX_AB)
    assert ia["n_cells"] + ib["n_cells"] == iab["n_cells"]
    for k, v in ab.items():
        assert v == pytest.approx(a[k] + b[k], abs=0.01)


def test_calendar_aoi_variants_and_reliability(api):
    point = {"type": "point", "lat": -13.5, "lon": -72.0, "radius_km": 2}
    body = _ok(api.post("/api/v1/calendar", json={"aoi": point}))
    assert body["aoi"]["n_cells"] >= 1
    if body["reliability"] == "baja":
        assert any("Confiabilidad baja" in n for n in body["notes"])
    poly = {"type": "Polygon", "coordinates": [[[-72.5, -13.6], [-72.1, -13.6], [-72.1, -13.3],
                                                [-72.5, -13.3], [-72.5, -13.6]]]}
    body = _ok(api.post("/api/v1/calendar", json={"aoi": {"type": "geojson", "geometry": poly}}))
    assert body["aoi"]["type"] == "geojson" and body["aoi"]["area_km2"] > 1000


@pytest.mark.parametrize(("aoi", "fragment"), [
    ({"type": "bbox", "bbox": [-75, -16, -69, -10]}, "máximo permitido"),
    ({"type": "bbox", "bbox": [-72, -13, -73, -14]}, "bbox inválido"),
    ({"type": "region", "code": "nope"}, "Región desconocida"),
    ({"type": "point", "lat": -13.5, "lon": -72, "radius_km": 500}, "radius_km"),
    ({"type": "geojson", "geometry": {"type": "Point", "coordinates": [-72, -13]}},
     "Polygon o MultiPolygon"),
    ({"type": "geojson", "geometry": {"type": "Polygon", "coordinates": [
        [[-72, -13], [-71, -14], [-71, -13], [-72, -14], [-72, -13]]]}}, "no válida"),
])
def test_aoi_errors_are_422_in_spanish(api, aoi, fragment):
    resp = api.post("/api/v1/calendar", json={"aoi": aoi})
    assert resp.status_code == 422
    assert fragment in resp.json()["detail"]


def test_schema_errors_are_422(api):
    resp = api.post("/api/v1/calendar", json={"aoi": {"type": "circle"}})
    assert resp.status_code == 422 and "Solicitud inválida" in resp.json()["detail"]


def test_anomaly_default_and_explicit(api):
    body = _ok(api.post("/api/v1/anomaly", json={"aoi": REG}))
    assert (body["year"], body["month"]) == (2026, 11) and body["provisional"]
    assert body["satellite"] == "N20"
    for k in ("median", "anomaly_abs", "anomaly_pct", "percentile", "percentile_sensor",
              "category", "band_p10", "band_p90", "reliability"):
        assert k in body
    body = _ok(api.post("/api/v1/anomaly", json={"aoi": REG, "year": 2015, "month": 9}))
    assert body["source"] == "modis_observed" and body["value"] > 0
    assert api.post("/api/v1/anomaly", json={"aoi": REG, "year": 2015}).status_code == 422


def test_hotspots_csv(api):
    req = {"aoi": {"type": "bbox", "bbox": BBOX_A}, "start": "2025-08-01", "end": "2025-09-30"}
    resp = api.post("/api/v1/hotspots", json=req)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.headers["x-data-mode"] == "synthetic"
    assert resp.content.startswith(b"\xef\xbb\xbf")  # BOM: Excel en Windows
    rows = list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert len(rows) == int(resp.headers["x-row-count"]) > 0
    w, s, e, n = BBOX_A
    assert all(w <= float(r["lon"]) <= e and s <= float(r["lat"]) <= n for r in rows)
    assert all(r["data_mode"] == "synthetic" for r in rows)
    assert all("2025-08-01" <= r["local_date"] <= "2025-09-30" for r in rows)


def test_hotspots_geojson_and_limits(api):
    req = {"aoi": {"type": "bbox", "bbox": BBOX_A}, "start": "2025-08-01",
           "end": "2025-08-10", "format": "geojson"}
    body = _ok(api.post("/api/v1/hotspots", json=req))
    assert body["type"] == "FeatureCollection" and body["n_features"] == len(body["features"])
    too_long = {**req, "start": "2010-01-01", "end": "2025-12-31"}
    assert "máximo" in api.post("/api/v1/hotspots", json=too_long).json()["detail"]
    backwards = {**req, "start": "2025-09-01", "end": "2025-08-01"}
    assert api.post("/api/v1/hotspots", json=backwards).status_code == 422
    # /hotspots NO exime a las regiones del límite de área
    region = {**req, "aoi": REG}
    assert api.post("/api/v1/hotspots", json=region).status_code == 422


def test_map_cells(api):
    body = _ok(api.post("/api/v1/map/cells", json={"aoi": REG, "year": 2025, "month": 9}))
    assert body["n_cells_with_data"] == len(body["features"]) > 0
    f = body["features"][0]
    ring = f["geometry"]["coordinates"][0]
    assert f["geometry"]["type"] == "Polygon" and ring[0] == ring[-1]
    assert f["properties"]["value"] > 0
    bad = api.post("/api/v1/map/cells", json={"aoi": REG, "year": 1990, "month": 1})
    assert bad.status_code == 422


def test_forecast_pending(api):
    body = _ok(api.post("/api/v1/forecast", json={"region_code": "peru_sur"}))
    assert body["available"] is False and any("Fase 7" in n for n in body["notes"])
    assert api.post("/api/v1/forecast", json={"region_code": "x"}).status_code == 422


def test_meta(api):
    body = _ok(api.get("/api/v1/meta"))
    assert "DIURNAS" in body["unit_description"]
    assert "band_p10" in body["band_description"]
    assert body["validation"]["acceptance"]["passed"]
    assert body["limits"]["max_csv_years"] == 5
    assert {r["pair"] for r in body["harmonization"]["regional_ratios"]} >= {"SNPP->AQUA"}
    assert "peru_sur" in body["regions"] and "PE-CUS" in body["regions"]


def test_docs_have_examples(api):
    spec = api.get("/openapi.json").json()
    schema = spec["components"]["schemas"]["CalendarRequest"]
    assert schema.get("examples")
    assert "/api/v1/calendar" in spec["paths"]


def test_precompute_cache(api, pipeline_home):
    from api.db import Repository
    from api.services import cache

    repo = Repository(pipeline_home.settings)
    files = cache.precompute(repo)
    assert len(files) == 2 * len(repo.regions) and all(f.is_file() for f in files)
    cached = cache.read(repo, "calendar", "peru_sur")
    live = api.post("/api/v1/calendar", json={"aoi": REG}).json()
    assert cached["cells"] == live["cells"]


def test_not_ready_returns_503(tmp_path):
    from firecal.settings import PROJECT_ROOT, load_params

    settings = Settings(env=EnvSettings(_env_file=None),
                        params=load_params(PROJECT_ROOT / "config" / "settings.yaml"),
                        paths=Paths(home=tmp_path))
    client = TestClient(create_app(settings))
    assert client.get("/health").json()["data_ready"] is False
    resp = client.get("/api/v1/meta")
    assert resp.status_code == 503 and "pipeline" in resp.json()["detail"]
