"""Tests de la capa del plan (A + C): deduplicación, constelación, anomalía y GET /api/*."""

from __future__ import annotations

import csv
import io
from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from firecal.plan.events import confidence_norm, deduplicate
from firecal.plan.query import category, era_of


# ------------------------------------------------------------------ unidades (sin pipeline)
def test_deduplicate_keeps_max_frp_per_cell_day():
    df = pd.DataFrame({
        "id": [1, 2, 3, 4],
        "sensor": ["MODIS", "VIIRS", "VIIRS", "VIIRS"],
        "px1km_id": [10, 10, 10, 11],
        "local_date": [date(2020, 8, 1)] * 3 + [date(2020, 8, 1)],
        "frp": [5.0, 12.0, None, 3.0],
    })
    out = deduplicate(df).set_index("px1km_id")
    assert len(out) == 2
    assert out.loc[10, "id"] == 2 and out.loc[10, "n_detecciones"] == 3
    assert out.loc[10, "sensores"] == "MODIS+VIIRS" and out.loc[11, "sensores"] == "VIIRS"


def test_deduplicate_different_days_are_different_events():
    df = pd.DataFrame({"id": [1, 2], "sensor": ["MODIS", "VIIRS"], "px1km_id": [10, 10],
                       "local_date": [date(2020, 8, 1), date(2020, 8, 2)], "frp": [1.0, 2.0]})
    assert len(deduplicate(df)) == 2


def test_confidence_norm():
    df = pd.DataFrame({"sensor": ["MODIS", "VIIRS", "VIIRS"],
                       "confidence_raw": ["85", "h", "n"],
                       "confidence_cat": ["high", "high", "nominal"]})
    assert list(confidence_norm(df)) == [0.85, 0.9, 0.6]


def test_era_and_category():
    assert era_of(2012, 1) == "MODIS" and era_of(2012, 2) == "MODIS+VIIRS"
    assert category(None) is None
    assert category(-1.5) == "muy por debajo" and category(0.0) == "normal"
    assert category(0.7) == "por encima" and category(3) == "muy por encima"


# ------------------------------------------------------------------ con el pipeline sintético
@pytest.fixture(scope="module")
def api(pipeline_home) -> TestClient:
    return TestClient(create_app(pipeline_home.settings))


def test_constellation_single_viirs(pipeline_home):
    """Nunca se suman dos VIIRS: antes del fin de S-NPP no hay eventos de N20 ni N21."""
    import duckdb

    from firecal.plan.events import events_dir
    glob = (events_dir(pipeline_home.settings) / "**" / "*.parquet").as_posix()
    sats = dict(duckdb.sql(f"SELECT satelite, min(fecha_local) FROM read_parquet('{glob}', "
                           "hive_partitioning=true) GROUP BY 1").fetchall())
    assert "N21" not in sats
    assert set(sats) <= {"AQUA", "TERRA", "SNPP", "N20"}
    assert min(sats.values()) >= date(2003, 1, 1)
    m = pipeline_home.plan_meta
    assert m["n_eventos"] < m["n_detecciones_constelacion"] <= m["n_detecciones_limpias"]


def test_departamentos(api):
    body = api.get("/api/departamentos").json()
    codes = {d["code"] for d in body["departamentos"]}
    assert {"PE-CUS", "PE-PUN", "PE-APU", "PE-AYA", "PE-MDD"} == codes
    assert body["data_mode"] == "synthetic" and any("sintéticos" in n for n in body["notes"])


def test_calendario_departamento(api):
    r = api.get("/api/calendario", params={"departamento": "pe-cus", "fecha_inicio": "2015-01",
                                           "fecha_fin": "2016-12"})
    assert r.status_code == 200, r.text
    assert "X-Process-Time-ms" in r.headers
    b = r.json()
    assert b["anios"] == [2015, 2016] and len(b["matriz_n_eventos"]) == 2
    assert all(len(row) == 12 for row in b["matriz_n_eventos"])
    assert len(b["celdas"]) == 24 and all(c["era"] == "MODIS+VIIRS" for c in b["celdas"])
    assert all(c["anomalia"] is not None for c in b["celdas"])


def test_calendario_anomaly_without_sensor_jump(api):
    """Con A + C la anomalía media no salta al entrar VIIRS (feb-2012)."""
    b = api.get("/api/calendario", params={"departamento": "PE-CUS"}).json()
    df = pd.DataFrame(b["celdas"]).dropna(subset=["anomalia"])
    before = df[(df["anio"] >= 2007) & (df["anio"] <= 2011)]["anomalia"].median()
    after = df[(df["anio"] >= 2013) & (df["anio"] <= 2017)]["anomalia"].median()
    assert abs(after - before) < 1.0
    # El conteo crudo sí salta (VIIRS detecta más): por eso existe la anomalía por era.
    raw = pd.DataFrame(b["celdas"])
    n_before = raw[(raw["anio"] >= 2007) & (raw["anio"] <= 2011)]["n_eventos"].sum()
    n_after = raw[(raw["anio"] >= 2013) & (raw["anio"] <= 2017)]["n_eventos"].sum()
    assert n_after > n_before


def test_calendario_bbox_and_point(api):
    r1 = api.get("/api/calendario", params={"bbox": "-72.6,-13.8,-71.8,-13.2"})
    r2 = api.get("/api/calendario", params={"lat": -13.5, "lon": -72.2, "radio_km": 30})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["aoi"]["tipo"] == "bbox" and r2.json()["aoi"]["tipo"] == "punto"


@pytest.mark.parametrize(("params", "status", "text"), [
    ({}, 422, "AOI vacío"),
    ({"departamento": "PE-LIM"}, 422, "Departamento desconocido"),
    ({"departamento": "PE-CUS", "fecha_inicio": "2020-05", "fecha_fin": "2019-01"}, 422,
     "Rango invertido"),
    ({"departamento": "PE-CUS", "fecha_inicio": "2020-13"}, 422, "AAAA-MM"),
    ({"bbox": "-80,-20,-60,0"}, 422, "Área demasiado grande"),
    ({"bbox": "-80,-5,-79.5,-4.5"}, 404, "Sin datos"),
    ({"departamento": "PE-CUS", "bbox": "-72,-14,-71,-13"}, 422, "un solo tipo"),
    ({"lat": -13.5, "lon": -72.0, "radio_km": 500}, 422, "radio_km"),
])
def test_calendario_errors(api, params, status, text):
    r = api.get("/api/calendario", params=params)
    assert r.status_code == status, r.text
    assert text in r.json()["detail"]


def test_anomalias(api):
    b = api.get("/api/anomalias", params={"departamento": "PE-PUN", "mes": "2016-09"}).json()
    assert b["mes"] == "2016-09" and b["era"] == "MODIS+VIIRS"
    assert b["mediana_hist"] is not None and b["anomalia"] is not None
    assert all(h["n_eventos"] >= 0 for h in b["historial"]) and len(b["historial"]) >= 5


def test_anomalia_matches_manual_calculation(api):
    """Caso de control (Q/A de lógica): la anomalía coincide con el cálculo a mano."""
    b = api.get("/api/anomalias", params={"departamento": "PE-CUS", "mes": "2014-08"}).json()
    vals = pd.Series([h["n_eventos"] for h in b["historial"]])
    med, iqr = vals.median(), max(vals.quantile(0.75) - vals.quantile(0.25), 1.0)
    assert b["mediana_hist"] == round(med, 1)
    assert b["anomalia"] == round((b["n_eventos"] - med) / iqr, 2)


def test_calendar_counts_match_csv(api):
    params = {"departamento": "PE-CUS", "fecha_inicio": "2019-08", "fecha_fin": "2019-08"}
    cal = api.get("/api/calendario", params=params).json()
    r = api.get("/api/hotspots.csv", params=params)
    assert r.status_code == 200 and r.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    assert len(rows) == cal["celdas"][0]["n_eventos"]
    assert {row["departamento"] for row in rows} == {"PE-CUS"}
    # Sin duplicados de celda y día tras la deduplicación.
    assert len({(row["celda_1km"], row["fecha_local"]) for row in rows}) == len(rows)


def test_hotspots_csv_limits(api):
    r = api.get("/api/hotspots.csv", params={"departamento": "PE-CUS", "fecha_inicio": "2010-01",
                                             "fecha_fin": "2020-01"})
    assert r.status_code == 422 and "demasiado largo" in r.json()["detail"]


def test_metadatos(api):
    b = api.get("/api/metadatos").json()
    assert b["armonizador"]["version"].startswith("plan-AC")
    assert "FIRMS" in b["creditos"]
    assert b["umbral_confianza"]["minimo"] == "nominal"
    assert "PE-CUS" in b["cobertura"]["departamentos"]


def test_frontend_served(api):
    r = api.get("/")
    assert r.status_code == 200 and "FireCal" in r.text
