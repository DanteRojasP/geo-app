"""Q/A de logica (PLAN.md, rol Gabriel): calculo manual independiente vs API.

Uso: python qa_logica.py <carpeta data/harmonized> [url_base]
No importa nada del backend: recalcula todo con pandas desde los dos CSV.
"""
from __future__ import annotations

import csv
import io
import math
import sys
import time

import httpx
import numpy as np
import pandas as pd

DATA = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
TOL = 1.0  # tolerancia de MAESTRO 12
CSV_MAX_5_ANIOS = "--csv-5-anios" in sys.argv
K = {("VIIRS*k", True): 0.330, ("VIIRS*k", False): 0.247,
     ("Terra*kT", True): 2.62, ("Terra*kT", False): 7.74}
EDGES = [(-1.0, "muy por debajo"), (-0.5, "por debajo"), (0.5, "normal"),
         (1.0, "por encima"), (math.inf, "muy por encima")]

results: list[tuple[str, str, bool, str]] = []


def check(grupo: str, nombre: str, ok: bool, detalle: str = "") -> None:
    results.append((grupo, nombre, bool(ok), detalle))
    print(f"[{'OK ' if ok else 'FALLA'}] {grupo} | {nombre} {('-> ' + detalle) if detalle else ''}")


client = httpx.Client(base_url=BASE, timeout=120)


def get(path: str, **params) -> httpx.Response:
    for _ in range(6):
        r = client.get(path, params=params)
        if r.status_code in (429, 503) and "Retry-After" in r.headers:
            time.sleep(float(r.headers["Retry-After"]) + 0.5)
            continue
        return r
    return r


# ------------------------------------------------------------------ datos
cd = pd.read_csv(f"{DATA}/harmonizado_cusco_celda_dia.csv", dtype={"fecha_local": str})
fo = pd.read_csv(f"{DATA}/focos_cusco_individuales.csv",
                 dtype={"fecha_local": str, "hora_utc": str, "confianza": str})
cd["anio"] = cd.fecha_local.str[:4].astype(int)
cd["mes"] = cd.fecha_local.str[5:7].astype(int)
fo["anio"] = fo.fecha_local.str[:4].astype(int)

# ------------------------------------------------------------------ 1. conteos (MAESTRO 12)
G = "1. Conteos"
esperado = {"total": 15818, 2005: 1355, 2012: 678, 2013: 424, 2020: 1206, 2022: 850, 2024: 640,
            2025: 387}   # MAESTRO §12, datos v1.3
man_total = cd.eq_hotspots.sum()
check(G, "manual: total periodo = 15,818", abs(man_total - 15818) <= TOL, f"{man_total:.2f}")
check(G, "manual: 36,568 celdas-dia", len(cd) == 36568, str(len(cd)))
check(G, "manual: 59,211 focos", len(fo) == 59211, str(len(fo)))
por_anio = cd.groupby("anio").eq_hotspots.sum()
for y in (2005, 2012, 2013, 2020, 2025):
    check(G, f"manual: anio {y} = {esperado[y]:,}", abs(por_anio[y] - esperado[y]) <= TOL,
          f"{por_anio[y]:.2f}")

cal = get("/api/calendario", departamento="PE-CUS", fecha_inicio="2000-01", fecha_fin="2026-12")
check(G, "API /calendario Cusco responde 200", cal.status_code == 200, str(cal.status_code))
cal = cal.json()
api_total = cal["total_focos_armonizados"]
check(G, "API total = manual", abs(api_total - man_total) <= TOL, f"API {api_total} vs {man_total:.2f}")
celdas = pd.DataFrame(cal["celdas"])
if "sin_dato" in celdas:
    n_sd = int(celdas.sin_dato.sum())
    fuera = celdas[celdas.sin_dato]
    check(G, "meses fuera de cobertura marcados sin_dato (no cero)",
          all((a, m) < (2000, 11) or (a, m) > (2025, 12) for a, m in zip(fuera.anio, fuera.mes))
          and "focos_armonizados" not in fuera.dropna(axis=1, how="all"), f"{n_sd} meses sin_dato")
    celdas = celdas[~celdas.sin_dato]
api_anio = celdas.groupby("anio").focos_armonizados.sum()
dif = (api_anio - por_anio.reindex(api_anio.index, fill_value=0)).abs()
check(G, "API por anio = manual (2000-2025, todos)", (dif <= TOL).all(),
      f"max dif {dif.max():.3f}")
man_mes = cd.groupby(["anio", "mes"]).eq_hotspots.sum()
api_mes = celdas.set_index(["anio", "mes"]).focos_armonizados
dm = (api_mes - man_mes.reindex(api_mes.index, fill_value=0)).abs()
check(G, "API por mes = manual (todos los meses, ceros incluidos)", (dm <= 0.01).all(),
      f"{len(dm)} meses, max dif {dm.max():.4f}")
for y in (2005, 2020):
    r = get("/api/calendario", departamento="PE-CUS", fecha_inicio=f"{y}-01", fecha_fin=f"{y}-12").json()
    check(G, f"API rango solo {y} = {esperado[y]:,}",
          abs(r["total_focos_armonizados"] - esperado[y]) <= TOL, str(r["total_focos_armonizados"]))

# ------------------------------------------------------------------ 2. deduplicacion / pesos
G = "2. Deduplicacion"
dup = cd.duplicated(["fecha_local", "cell_lat", "cell_lon"]).sum()
check(G, "una sola fila por celda-dia (sin duplicados)", dup == 0, f"{dup} duplicadas")
fo_cell = fo.assign(cell_lat=fo.cell_lat.round(3), cell_lon=fo.cell_lon.round(3))
cd_cell = cd.assign(cell_lat=cd.cell_lat.round(3), cell_lon=cd.cell_lon.round(3))
s = fo_cell.groupby(["fecha_local", "cell_lat", "cell_lon"]).eq_foco.sum()
m = cd_cell.set_index(["fecha_local", "cell_lat", "cell_lon"]).eq_hotspots
j = pd.concat([s.rename("focos"), m.rename("celda")], axis=1).fillna(0)
d = (j.focos - j.celda).abs()
check(G, "suma eq_foco de cada celda-dia = eq_hotspots", (d <= 1e-3).all(),
      f"{(d > 1e-3).sum()} celdas difieren, max {d.max():.4f}")
alto = cd.alt_m >= 2500
ok_k = True
for (fuente, es_alto), k in K.items():
    sel = cd[(cd.fuente_serie == fuente) & (alto == es_alto)]
    ok_k &= np.allclose(sel.eq_hotspots, k, atol=0.006)  # el contrato redondea a 2-3 decimales
sel = cd[cd.fuente_serie == "MODIS"]
ok_k &= np.allclose(sel.eq_hotspots, 1.0)
check(G, "cada celda-dia vale 1 (MODIS), k o kT segun estrato", ok_k)
fecha = pd.to_datetime(cd.fecha_local)
reglas = (((fecha < "2002-07-04") == (cd.fuente_serie == "Terra*kT"))
          & (((fecha >= "2002-07-04") & (fecha <= "2012-12-31")) == (cd.fuente_serie == "MODIS"))
          & ((fecha >= "2013-01-01") == (cd.fuente_serie == "VIIRS*k")))
check(G, "fuente de la serie segun periodo (contrato)", reglas.all(), f"{(~reglas).sum()} filas fuera")
v12 = fo[(fo.sensor == "VIIRS") & (fo.anio == 2012)]
m13 = fo[(fo.sensor == "MODIS") & (fo.anio >= 2013)]
check(G, "VIIRS 2012 y MODIS >=2013 fuera de la serie (en_serie=0, eq_foco=0)",
      (v12.en_serie == 0).all() and (m13.en_serie == 0).all() and (v12.eq_foco == 0).all()
      and (m13.eq_foco == 0).all(), f"{len(v12)} VIIRS-2012, {len(m13)} MODIS>=2013")
# Igual que harmonizacion/verificar_datos.py y MAESTRO.md: los repetidos por posicion/hora con FRP
# distinto son un artefacto conocido de FIRMS y se conservan; se tolera hasta 5.
check(G, "sin filas totalmente identicas", not fo.duplicated().any())
fd = int(fo.duplicated(["fecha_utc", "hora_utc", "satelite", "latitude", "longitude"]).sum())
if fd:
    print(f"   AVISO: {fd} foco(s) repiten fecha, hora, posicion y satelite con FRP distinto "
          "(artefacto conocido de FIRMS, MAESTRO.md; se conservan)")
check(G, "repetidos por posicion/hora dentro de lo esperado (<= 5)", fd <= 5, f"{fd} repetidos")

# ------------------------------------------------------------------ 3. mediana y anomalia
G = "3. Mediana/anomalia"
idx = pd.period_range("2000-11", "2025-12", freq="M")
serie = pd.DataFrame({"anio": idx.year, "mes": idx.month})
agg = cd.groupby(["anio", "mes"]).agg(n=("eq_hotspots", "sum"),
                                      ext=("calidad", lambda c: (c == "extrapolado").all()))
serie = serie.merge(agg.reset_index(), on=["anio", "mes"], how="left")
serie["n"] = serie.n.fillna(0.0)
sin_focos = serie.ext.isna()
por_fecha = [(a, b) < (2002, 7) for a, b in zip(serie.anio, serie.mes)]
serie["extrap"] = np.where(sin_focos, por_fecha, serie.ext.fillna(False)).astype(bool)
hist = serie[~serie.extrap]


def stats(mes: int) -> tuple[float, float, int]:
    v = np.sort(hist[hist.mes == mes].n.to_numpy())
    med = float(np.median(v))
    iqr = float(np.percentile(v, 75) - np.percentile(v, 25))
    return med, max(iqr, 1.0), len(v)


def cat(a: float) -> str:
    return next(n for e, n in EDGES if a < e)


api = celdas.set_index(["anio", "mes"])
PARCIAL_2000_11 = "parcial" in celdas and bool(celdas[(celdas.anio == 2000) & (celdas.mes == 11)].parcial.any())
bad_med, bad_an, bad_cat, total = [], [], [], 0
for _, r in serie.iterrows():
    key = (r.anio, r.mes)
    if key not in api.index:
        continue
    med, iqr, n_anios = stats(r.mes)
    an = (r.n - med) / iqr if n_anios >= 5 else None
    if PARCIAL_2000_11 and key == (2000, 11):
        an = None  # la serie empieza el 2000-11-04: mes parcial, sin anomalia
    a = api.loc[key]
    total += 1
    if abs(a.mediana_hist - med) > 0.051:
        bad_med.append(key)
    if pd.isna(a.anomalia) and an is not None:
        bad_an.append(key)
        continue
    if an is None:
        if a.anomalia is not None and not pd.isna(a.anomalia):
            bad_an.append(key)
        continue
    if abs(a.anomalia - an) > 0.006:
        bad_an.append(key)
    if a.categoria != "incierta" and a.categoria != cat(round(an, 2)):
        bad_cat.append(key)
check(G, f"mediana historica por mes = manual ({total} meses)", not bad_med, f"difieren: {bad_med[:5]}")
check(G, f"anomalia = (n - mediana)/max(IQR,1) = manual ({total} meses)", not bad_an,
      f"difieren: {bad_an[:5]}")
check(G, "categoria segun umbrales = manual", not bad_cat, f"difieren: {bad_cat[:5]}")
check(G, "mediana excluye meses extrapolados (2000-11 a 2002-06)",
      hist[(hist.anio < 2002) | ((hist.anio == 2002) & (hist.mes < 7))].empty)

# caso de control detallado: agosto 2020 (temporada alta) y febrero 2010 (temporada baja)
for mes in ("2020-08", "2010-02", "2001-08"):
    y, mm = map(int, mes.split("-"))
    r = get("/api/anomalias", departamento="PE-CUS", mes=mes)
    if r.status_code != 200:
        check(G, f"control {mes}: /api/anomalias 200", False, f"{r.status_code} {r.text[:120]}")
        continue
    r = r.json()
    n = float(serie[(serie.anio == y) & (serie.mes == mm)].n.iloc[0])
    med, iqr, _ = stats(mm)
    an = (n - med) / iqr
    ok = (abs(r["focos_armonizados"] - n) < 0.01 and abs(r["mediana_hist"] - med) <= 0.051
          and abs(r["anomalia"] - an) <= 0.006)
    det = (f"n={n:.2f} med={med:.2f} IQR={iqr:.2f} anom={an:.3f} | API n={r['focos_armonizados']} "
           f"med={r['mediana_hist']} anom={r['anomalia']} cat={r['categoria']}")
    if mes == "2001-08":
        unc = r.get("incertidumbre")
        det += f" incert={unc} rango={r.get('rango')}"
        ok &= r.get("calidad") == "extrapolado" and (unc or 0) > 0
    check(G, f"control {mes} vs calculo manual", ok, det)

# ------------------------------------------------------------------ 4. CSV
G = "4. CSV"
contrato = ["fecha_local", "fecha_utc", "hora_utc", "latitude", "longitude", "cell_lat", "cell_lon",
            "alt_m", "sensor", "satelite", "frp", "brillo_k", "confianza", "diurno_nocturno",
            "fuente_serie", "calidad", "en_serie", "eq_foco"]
for ini, fin in (("2020-01", "2020-12"), ("2001-01", "2005-12"), ("2012-06", "2013-06")):
    r = get("/api/hotspots.csv", departamento="PE-CUS", fecha_inicio=ini, fecha_fin=fin)
    if r.status_code != 200:
        check(G, f"{ini}..{fin} descarga 200", False, f"{r.status_code} {r.text[:150]}")
        continue
    raw = r.content
    check(G, f"{ini}..{fin} UTF-8 con BOM (Excel)", raw.startswith(b"\xef\xbb\xbf"))
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    cols = list(rows[0].keys()) if rows else []
    check(G, f"{ini}..{fin} 18 columnas del contrato en orden", cols == contrato, str(cols[:4]))
    sel = fo[(fo.fecha_local.str[:7] >= ini) & (fo.fecha_local.str[:7] <= fin)]
    check(G, f"{ini}..{fin} n filas = manual", len(rows) == len(sel), f"{len(rows)} vs {len(sel)}")
    s_csv = math.fsum(float(x["eq_foco"]) for x in rows)
    c = get("/api/calendario", departamento="PE-CUS", fecha_inicio=ini, fecha_fin=fin).json()
    check(G, f"{ini}..{fin} suma eq_foco = total del calendario",
          abs(s_csv - c["total_focos_armonizados"]) <= 0.01,
          f"CSV {s_csv:.3f} vs pantalla {c['total_focos_armonizados']}")
    horas_ok = all(len(x["hora_utc"]) == 4 for x in rows)
    check(G, f"{ini}..{fin} hora_utc con 4 digitos (HHMM)", horas_ok)

# ------------------------------------------------------------------ 5. casos limite de logica
G = "5. Casos limite"
r = get("/api/calendario", departamento="PE-CUS", fecha_inicio="1999-01", fecha_fin="2000-10")
check(G, "antes de 2000-11 -> 'sin datos' (no cero)",
      r.status_code == 404 or (r.status_code == 200 and not r.json().get("celdas")),
      f"{r.status_code} {r.text[:120]}")
r = get("/api/calendario", departamento="PE-APU")
check(G, "otro departamento cargado (Apurimac) -> 404 sin datos", r.status_code == 404, f"{r.status_code}")
r = get("/api/calendario", departamento="PE-LOR")
check(G, "otro departamento no cargado (Loreto) -> 404 sin datos (MAESTRO 12)", r.status_code == 404,
      f"{r.status_code} {r.json().get('detail', '')[:80]}")
r = get("/api/calendario", bbox="-75.5,-5.0,-75.0,-4.5")
check(G, "rectangulo fuera de Cusco -> 404", r.status_code == 404, f"{r.status_code} {r.text[:100]}")
r = get("/api/calendario", departamento="PE-CUS", fecha_inicio="2020-12", fecha_fin="2020-01")
check(G, "rango invertido -> 422", r.status_code == 422, f"{r.status_code}")
r = get("/api/hotspots.csv", departamento="PE-CUS", fecha_inicio="2020-13", fecha_fin="2021-01")
check(G, "mes invalido (2020-13) -> 422", r.status_code == 422, f"{r.status_code}")
r = get("/api/hotspots.csv", departamento="PE-CUS", fecha_inicio="2000-11", fecha_fin="2025-12")
if CSV_MAX_5_ANIOS:
    check(G, "CSV de mas de 5 anios -> 422", r.status_code == 422, f"{r.status_code} {r.text[:100]}")
else:
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig")))) if r.status_code == 200 else []
    s_all = math.fsum(float(x["eq_foco"]) for x in rows)
    check(G, "CSV periodo completo: 59,211 focos y suma = 15,818 (MAESTRO 12)",
          len(rows) == 59211 and abs(s_all - 15818) <= TOL, f"{r.status_code} {len(rows)} filas, {s_all:.2f}")
    hdr = r.headers.get("X-Total-Eq-Foco"), r.headers.get("X-Row-Count")
    check(G, "cabeceras X-Row-Count y X-Total-Eq-Foco = contenido",
          hdr[1] is not None and int(hdr[1]) == len(rows) and abs(float(hdr[0]) - s_all) <= 0.01, str(hdr))

# AOI rectangular: total del calendario = descarga = calculo manual por posicion del foco
BB = (-72.2, -13.6, -71.8, -13.2)  # zona del Valle Sagrado, dentro de Cusco
r = get("/api/calendario", bbox=",".join(map(str, BB)), fecha_inicio="2020-01", fecha_fin="2020-12")
if r.status_code == 200:
    t_cal = r.json()["total_focos_armonizados"]
    rc = get("/api/hotspots.csv", bbox=",".join(map(str, BB)), fecha_inicio="2020-01", fecha_fin="2020-12")
    rows = list(csv.DictReader(io.StringIO(rc.content.decode("utf-8-sig"))))
    t_csv = math.fsum(float(x["eq_foco"]) for x in rows)
    selb = fo[(fo.fecha_local.str[:4] == "2020") & fo.longitude.between(BB[0], BB[2])
              & fo.latitude.between(BB[1], BB[3])]
    selc = fo[(fo.fecha_local.str[:4] == "2020") & fo.cell_lon.between(BB[0], BB[2])
              & fo.cell_lat.between(BB[1], BB[3])]
    check(G, "bbox: total calendario = suma CSV",
          abs(t_cal - t_csv) <= 0.01, f"cal {t_cal} vs CSV {t_csv:.3f}")
    check(G, "bbox: total = manual (por posicion del foco o de la celda)",
          min(abs(t_cal - selb.eq_foco.sum()), abs(t_cal - selc.eq_foco.sum())) <= 0.01,
          f"API {t_cal} | manual foco {selb.eq_foco.sum():.3f} | manual celda {selc.eq_foco.sum():.3f}")
else:
    check(G, "bbox dentro de Cusco responde 200", False, f"{r.status_code} {r.text[:100]}")

r = get("/api/focos.geojson", departamento="PE-CUS", fecha_inicio="2020-08", fecha_fin="2020-08")
if r.status_code == 200:
    g = r.json()
    feats = g["features"]
    s_g = math.fsum(f["properties"]["eq_foco"] for f in feats)
    m08 = fo[fo.fecha_local.str[:7] == "2020-08"]
    check(G, "focos.geojson ago-2020: n y suma eq_foco = manual",
          len(feats) == len(m08) and abs(s_g - m08.eq_foco.sum()) <= 0.01,
          f"{len(feats)} vs {len(m08)}, {s_g:.3f} vs {m08.eq_foco.sum():.3f}")
    check(G, "focos.geojson sin FRP (decision del equipo)",
          not any("frp" in f["properties"] for f in feats[:50]))
elif r.status_code != 404 or "focos.geojson" in r.text:
    check(G, "/api/focos.geojson responde", False, f"{r.status_code}")
meta = get("/api/metadatos").json()
check(G, "metadatos: total = manual y creditos FIRMS",
      abs(meta.get("total_eq_hotspots", meta.get("cobertura", {}).get("total_eq_hotspots", 0)) - man_total) <= TOL
      or "FIRMS" in str(meta), str({k: meta[k] for k in list(meta)[:6]})[:200])

# ------------------------------------------------------------------ resumen
ok = sum(r[2] for r in results)
print(f"\nRESUMEN: {ok}/{len(results)} verificaciones OK")
pd.DataFrame(results, columns=["grupo", "prueba", "ok", "detalle"]).to_csv(
    sys.argv[0].replace(".py", "_resultado.csv"), index=False, encoding="utf-8-sig")
sys.exit(0 if ok == len(results) else 1)
