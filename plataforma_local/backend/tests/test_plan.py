"""Tests con los datos reales de Cusco (MAESTRO.md v1.2, casos de prueba de §12)."""

from __future__ import annotations

import csv
import io

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from firecal.plan.query import category, color_breaks, month_quality
from firecal.plan.sources import COLS_FOCOS, CONTROL


def _csv_rows(resp) -> list[dict]:
    return list(csv.DictReader(io.StringIO(resp.content.decode("utf-8-sig"))))


# ------------------------------------------------------------------ unidades
def test_month_quality_follows_contract():
    assert month_quality(2001, 5) == ("extrapolado", "Terra*kT")
    assert month_quality(2002, 7) == ("mixto", "Terra*kT + MODIS")
    assert month_quality(2012, 12) == ("referencia", "MODIS")
    assert month_quality(2013, 1) == ("calibrado", "VIIRS*k")


def test_color_breaks_quantiles_and_category():
    assert color_breaks([0, 0, None]) == []
    b = color_breaks([float(x) for x in range(1, 101)])
    assert b == sorted(b) and len(b) == 4 and b[0] in (50, 51) and b[-1] in (99, 100)
    assert category(None) is None and category(0.0) == "normal" and category(2) == "muy por encima"


# ------------------------------------------------------------------ carga y contrato
def test_load_matches_maestro_controls(plan_home):
    c = plan_home.meta["controles"]
    for name in ("celda_dia", "focos"):
        assert c[name]["coincide_maestro"], c[name]["problemas"]
        assert c[name]["filas"] == CONTROL[name]["filas"]
        assert c[name]["sha256"] == CONTROL[name]["sha256"]
    f = plan_home.meta["factores"]
    assert f["VIIRS*k|alto"] == 0.33 and f["VIIRS*k|bajo"] == 0.247
    assert f["Terra*kT|alto"] == 2.619 and f["MODIS|bajo"] == 1.0


def test_contract_change_is_detected(plan_home, monkeypatch):
    from firecal.plan import events

    monkeypatch.setitem(events.CONTROL, "focos", {**CONTROL["focos"], "filas": 1})
    with pytest.raises(events.DataContractError, match="filas"):
        events.read_sources(strict=True)


# ------------------------------------------------------------------ API
@pytest.fixture(scope="module")
def api(plan_home) -> TestClient:
    return TestClient(create_app(plan_home.settings))


def _cal(api, **params):
    r = api.get("/api/calendario", params={"departamento": "PE-CUS", **params})
    assert r.status_code == 200, r.text
    return r.json()


def test_health_and_departamentos(api):
    assert api.get("/health").json() == {"status": "ok", "data_mode": "real", "data_ready": True}
    b = api.get("/api/departamentos").json()
    assert [d["code"] for d in b["departamentos"]] == ["PE-CUS"]
    assert b["geojson"]["features"][0]["geometry"]["type"] == "MultiPolygon"


def test_maestro_case_whole_period(api):
    b = _cal(api)
    assert abs(b["total_eq_hotspots"] - 15732) <= 1
    assert sum(c.get("celdas_dia", 0) for c in b["celdas"]) == 36260
    assert b["fecha_inicio"] == "2000-11" and b["fecha_fin"] == "2025-12"
    assert "Focos armonizados" in b["unidad"]


@pytest.mark.parametrize(("year", "expected"), [(2005, 1355), (2012, 678), (2013, 424),
                                                (2020, 1206), (2025, 385)])
def test_maestro_cases_by_year(api, year, expected):
    b = _cal(api, fecha_inicio=f"{year}-01", fecha_fin=f"{year}-12")
    assert abs(b["total_eq_hotspots"] - expected) <= 1


@pytest.mark.parametrize("params", [
    {"departamento": "PE-CUS", "fecha_inicio": "1999-01", "fecha_fin": "2000-10"},
    {"departamento": "PE-PUN"},
    {"bbox": "-80,-5,-79.5,-4.5"},
    {"lat": -5.0, "lon": -80.0, "radio_km": 10},
])
def test_maestro_sin_datos_not_zero(api, params):
    r = api.get("/api/calendario", params=params)
    assert r.status_code == 404 and "Sin datos" in r.json()["detail"]


def test_months_outside_coverage_are_sin_dato(api):
    b = _cal(api, fecha_inicio="2000-01", fecha_fin="2001-12")
    by = {(c["anio"], c["mes"]): c for c in b["celdas"]}
    assert by[(2000, 10)]["sin_dato"] and "eq_hotspots" not in by[(2000, 10)]
    assert not by[(2000, 11)]["sin_dato"] and by[(2000, 11)]["parcial"]
    assert by[(2001, 1)]["calidad"] == "extrapolado"
    assert b["matriz_eq_hotspots"][0][9] is None                     # 2000-10: null, no 0
    assert any("extrapolado" in n for n in b["notes"])


def test_no_frp_and_no_eventos_in_api(api):
    text = api.get("/api/calendario", params={"departamento": "PE-CUS"}).text.lower()
    assert "frp" not in text and "evento" not in text


def test_download_whole_period_contract(api):
    r = api.get("/api/hotspots.csv", params={"departamento": "PE-CUS", "fecha_inicio": "2000-11",
                                             "fecha_fin": "2025-12"})
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf")
    rows = _csv_rows(r)
    assert list(rows[0].keys()) == COLS_FOCOS                        # 18 columnas, mismo orden
    assert len(rows) == 58779 and r.headers["X-Row-Count"] == "58779"
    assert abs(sum(float(x["eq_foco"]) for x in rows) - 15732.01) < 0.05
    assert all(len(x["hora_utc"]) == 4 for x in rows)                # texto con ceros a la izq.
    assert "cusco_2000-11_2025-12" in r.headers["Content-Disposition"]


@pytest.mark.parametrize("aoi", [
    {"departamento": "PE-CUS"},
    {"bbox": "-72.6,-13.8,-71.8,-13.2"},
    {"lat": -13.52, "lon": -71.97, "radio_km": 40},
])
def test_screen_total_equals_download_sum(api, aoi):
    """MAESTRO §12: Σ eq_foco de la descarga = total mostrado en pantalla."""
    q = {**aoi, "fecha_inicio": "2019-01", "fecha_fin": "2021-12"}
    cal = api.get("/api/calendario", params=q).json()
    rows = _csv_rows(api.get("/api/hotspots.csv", params=q))
    assert abs(sum(float(x["eq_foco"]) for x in rows) - cal["total_eq_hotspots"]) <= 1


def test_anomalias_with_daily_detail(api):
    b = api.get("/api/anomalias", params={"departamento": "PE-CUS", "mes": "2020-09"}).json()
    assert b["calidad"] == "calibrado" and b["mediana_hist"] is not None
    assert abs(sum(d["eq_hotspots"] for d in b["dias"]) - b["eq_hotspots"]) < 0.05
    assert len(b["historial"]) >= 20
    vals = sorted(h["eq_hotspots"] for h in b["historial"])
    assert b["mediana_hist"] == pytest.approx(vals[len(vals) // 2] if len(vals) % 2 else
                                              (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2,
                                              abs=0.01)
    r = api.get("/api/anomalias", params={"departamento": "PE-CUS", "mes": "2026-01"})
    assert r.status_code == 404


@pytest.mark.parametrize(("params", "status", "text"), [
    ({}, 422, "AOI vacío"),
    ({"departamento": "PE-CUS", "fecha_inicio": "2020-05", "fecha_fin": "2019-01"}, 422,
     "Rango invertido"),
    ({"departamento": "PE-CUS", "fecha_inicio": "2020-13"}, 422, "AAAA-MM"),
    ({"bbox": "-80,-20,-60,0"}, 422, "Área demasiado grande"),
    ({"departamento": "PE-CUS", "bbox": "-72,-14,-71,-13"}, 422, "un solo tipo"),
])
def test_calendario_errors(api, params, status, text):
    r = api.get("/api/calendario", params=params)
    assert r.status_code == status, r.text
    assert text in r.json()["detail"]


def test_legacy_v1_disabled_by_default(api):
    assert api.post("/api/v1/calendar", json={}).status_code in (404, 405)
    assert "/api/v1/calendar" not in api.get("/openapi.json").json()["paths"]


def test_metadatos(api):
    b = api.get("/api/metadatos").json()
    assert b["unidad"]["nombre"] == "Focos armonizados"
    assert all(v["coincide"] for v in b["controles_maestro"].values())
    assert any("FIRMS" in c for c in b["creditos"])
    assert b["armonizacion"]["serie"][2]["k"] == {"alto": 0.33, "bajo": 0.247}


def test_frontend_served(api):
    r = api.get("/")
    assert r.status_code == 200 and "FireCal Cusco" in r.text
