"""Ámbitos de Cusco: nivel de peligro (formato CENEPRED) e informes (firecal/plan/ambitos.py)."""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from firecal.plan.ambitos import (
    MIN_AREA_KM2,
    PARAMETROS,
    REF,
    clasificar,
    niveles_disponibles,
    pesos_ahp,
)

PROHIBIDAS = re.compile(r"\b(riesgo|alerta|evento|risk|alert|event)s?\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def api(plan_home) -> TestClient:
    return TestClient(create_app(plan_home.settings))


def _get(api, ruta, **params):
    r = api.get(ruta, params={"lang": "es", **params})
    assert r.status_code == 200, r.text
    return r


def test_pesos_saaty_consistentes():
    pesos, cr = pesos_ahp()
    assert set(pesos) == set(PARAMETROS) and sum(pesos.values()) == pytest.approx(1, abs=0.002)
    assert pesos["densidad"] > pesos["recurrencia"] > pesos["extremo"]
    assert cr < 0.10  # Saaty: matriz consistente


def test_clasificar_en_cuatro_niveles():
    assert [clasificar(x, True) for x in (0.9, 0.6, 0.3, 0.1)] == [
        "muy_alto",
        "alto",
        "medio",
        "bajo",
    ]
    assert clasificar(0.99, False) == "bajo"  # sin fuego: siempre bajo


def test_niveles_disponibles(api):
    d = _get(api, "/api/ambitos").json()
    niveles = [n["nivel"] for n in d["niveles"]]
    assert niveles == niveles_disponibles()
    assert niveles[:2] == ["provincia", "distrito"] and niveles[2:] == [
        f"pfaf_{i:02d}" for i in range(1, 13)
    ]
    por = {n["nivel"]: n for n in d["niveles"]}
    assert por["provincia"]["n_unidades"] == 13 and por["distrito"]["n_unidades"] == 108
    assert d["metodo"]["consistente"]


@pytest.mark.parametrize("nivel", ["provincia", "distrito", "pfaf_08", "pfaf_12"])
def test_tipificacion_ordenada_y_coherente(api, nivel):
    d = _get(api, f"/api/ambitos/{nivel}").json()
    us = d["unidades"]
    clasif = [u for u in us if u["nivel_peligro"] != "sin_clasificar"]
    assert len(clasif) >= 4
    assert [u["puesto"] for u in clasif] == sorted(u["puesto"] for u in clasif)
    for u in clasif:
        assert 0 <= u["indice"] <= 1
        if all(abs(u["indice"] - x) > 0.001 for x in (0.25, 0.5, 0.75)):  # índice redondeado
            assert u["nivel_peligro"] == clasificar(u["indice"], u["con_focos"])
    for u in us:
        if u["nivel_peligro"] == "sin_clasificar":
            assert u["area_km2"] < MIN_AREA_KM2 and u["indice"] is None
    assert {u["nivel_peligro"] for u in clasif} == {"muy_alto", "alto", "medio", "bajo"}


@pytest.mark.parametrize(
    ("nivel", "minimo"), [("provincia", 0.98), ("distrito", 0.98), ("pfaf_08", 0.99)]
)
def test_los_ambitos_cubren_el_fuego_de_cusco(api, nivel, minimo):
    """Las unidades suman casi todo el fuego de Cusco 2003-2025 (cada celda va a una sola).

    Los distritos y provincias son de INEI y el límite de la serie es de FAO GAUL: en el borde hay
    celdas que no caen en ningún distrito (~1.7 %). Las cuencas se recortan al límite GAUL."""
    us = _get(api, f"/api/ambitos/{nivel}").json()["unidades"]
    suma = sum(u["media_anual"] for u in us) * (REF[1] - REF[0] + 1)
    cal = _get(
        api,
        "/api/calendario",
        departamento="PE-CUS",
        fecha_inicio=f"{REF[0]}-01",
        fecha_fin=f"{REF[1]}-12",
    ).json()["total_focos_armonizados"]
    assert minimo * cal <= suma <= cal * 1.001
    cob = _get(api, f"/api/ambitos/{nivel}").json()["cobertura"]
    assert cob == pytest.approx(suma / cal, abs=0.001)


def test_un_nivel_con_pocas_unidades_no_se_clasifica(api):
    us = _get(api, "/api/ambitos/pfaf_01").json()["unidades"]
    assert len(us) == 1 and us[0]["nivel_peligro"] == "sin_clasificar"


def test_detalle_de_una_provincia(api):
    d = _get(api, "/api/ambitos/provincia/0809").json()  # La Convención
    u = d["unidad"]
    assert u["nombre"] == "La Convencion" and u["nivel_peligro"] in {"muy_alto", "alto"}
    assert len(d["frases"]) == 5 and d["informe"] == "/api/ambitos/provincia/0809/informe"
    assert set(d["serie_anual"]) == {str(a) for a in range(REF[0], REF[1] + 1)}
    assert u["media_anual"] == pytest.approx(sum(d["serie_anual"].values()) / 23, abs=0.1)


def test_csv_y_geojson(api):
    r = _get(api, "/api/ambitos/distrito.csv")
    lineas = r.content.decode("utf-8").splitlines()
    assert lineas[0].startswith("﻿puesto,codigo,nombre,provincia") and len(lineas) == 109
    assert "nivel_de_peligro.csv" in r.headers["Content-Disposition"]
    g = _get(api, "/api/ambitos/distrito.geojson").json()
    assert len(g["features"]) == 108
    p = g["features"][0]["properties"]
    assert {"codigo", "nombre", "nivel_peligro", "etiqueta", "color"} <= set(p)


@pytest.mark.parametrize("lang", ["es", "en"])
def test_informe_html(api, lang):
    r = api.get("/api/ambitos/distrito/080910/informe", params={"lang": lang})  # Pichari
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    h = r.text
    assert "Pichari" in h and "CENEPRED" in h and "<svg" in h and "FIRMS" in h
    assert ("Nivel de peligro por focos de calor" if lang == "es" else "Hotspot hazard level") in h
    assert ("Definiciones técnicas" if lang == "es" else "Technical definitions") in h
    assert "MOD14" in h and "VNP14IMG" in h and "type = 0" in h
    texto = re.sub(r"<[^>]+>", " ", h)
    assert not PROHIBIDAS.search(texto), PROHIBIDAS.search(texto)


def test_vocabulario_en_las_respuestas(api):
    for ruta in ("/api/ambitos", "/api/ambitos/provincia", "/api/ambitos/provincia/0803"):
        for lang in ("es", "en"):
            texto = api.get(ruta, params={"lang": lang}).text
            assert not PROHIBIDAS.search(texto), (ruta, lang, PROHIBIDAS.search(texto))


def test_errores(api):
    assert api.get("/api/ambitos/municipio").status_code == 404
    assert api.get("/api/ambitos/distrito/999999").status_code == 404
    assert api.get("/api/ambitos/distrito", params={"zona": "x"}).status_code == 422


def test_definiciones_tecnicas_en_la_api(api):
    for lang, palabra in (("es", "Foco de calor"), ("en", "Hotspot")):
        d = api.get("/api/ambitos", params={"lang": lang}).json()["metodo"]["definiciones"]
        assert set(d) == {"foco_de_calor", "foco_armonizado", "nivel_de_peligro"}
        assert d["foco_de_calor"].startswith(palabra) and "FIRMS" in d["foco_de_calor"]
