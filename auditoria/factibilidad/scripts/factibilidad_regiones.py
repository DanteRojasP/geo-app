"""Factibilidad de llevar la armonizacion de Cusco a otros departamentos del Peru.

Recalcula, con codigo independiente del equipo, lo que hace harmonizacion/firms_csv.py pero por
departamento: k (VIIRS->MODIS, 2013-19) y kT (Terra->Terra+Aqua, 2003-12), y mide con 2020-24
reservado cuanto falla cada factor. Primero se reproduce Cusco para saber si el metodo coincide.

Limite honesto: no hay altitud SRTM aqui (requiere Earth Engine), asi que NO se estratifica por
altitud (el equipo usa >= 2500 m / < 2500 m). Sirve para comparar departamentos entre si y contra
Cusco, no para fijar los factores finales.

Uso: python -I factibilidad_regiones.py <firms_raw> <adm1.geojson> <salida_csv>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

RAW, LIM, OUT = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
PASO = 0.01
CAL = ("2013-01-01", "2019-12-31")
VAL = range(2020, 2025)          # 2020-2024 reservado, como en MAESTRO
MIN_MES = 15                      # un mes necesita >= 15 celda-dias MODIS para medir su error

# ------------------------------------------------------------------ limites
feats = json.loads(LIM.read_text(encoding="utf-8-sig"))["features"]
deps = {}
for f in feats:
    iso = f["properties"]["shapeISO"].strip("*")
    deps.setdefault(iso, []).append(shape(f["geometry"]))
deps = {k: unary_union(v) for k, v in deps.items()}
NOMBRE = {f["properties"]["shapeISO"].strip("*"): f["properties"]["shapeName"].encode("latin-1", "ignore").decode("latin-1")
          for f in feats}
# Lima Metropolitana y Callao primero: son recortes pequenos dentro de Lima.
orden = sorted(deps, key=lambda k: deps[k].area)


def asignar(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    out = np.full(len(lon), "", dtype=object)
    for k in orden:
        g = deps[k]
        x0, y0, x1, y1 = g.bounds
        cand = np.flatnonzero((out == "") & (lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1))
        if len(cand):
            dentro = shapely.contains_xy(g, lon[cand], lat[cand])
            out[cand[dentro]] = k
    return out


# ------------------------------------------------------------------ datos
def cargar(patron: str, viirs: bool) -> pd.DataFrame:
    fs = sorted(RAW.glob(patron))
    anios = [re.search(r"20\d\d", f.name).group(0) for f in fs]
    assert len(set(anios)) == len(anios), "archivos repetidos por anio"
    cols = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "type"]
    d = pd.concat([pd.read_csv(f, usecols=cols, dtype={"confidence": str}) for f in fs], ignore_index=True)
    d = d[d["type"] == 0]
    if viirs:
        d = d[d["confidence"].isin(["n", "h"])]
    else:
        d = d[pd.to_numeric(d["confidence"], errors="coerce") >= 30]
    t = pd.to_numeric(d["acq_time"], errors="coerce").fillna(0).astype(int)
    ts = pd.to_datetime(d["acq_date"]) + pd.to_timedelta(t // 100, unit="h") + pd.to_timedelta(t % 100, unit="m")
    d = d.assign(loc=(ts - pd.Timedelta(hours=5)).dt.normalize(),
                 ci=np.floor(d.latitude.to_numpy() / PASO).astype(int),
                 cj=np.floor(d.longitude.to_numpy() / PASO).astype(int))
    d["dep"] = asignar(d.longitude.to_numpy(), d.latitude.to_numpy())
    return d.reset_index(drop=True)


mod = cargar("modis_*_Peru.csv", False)
vii = cargar("viirs-snpp_*_Peru.csv", True)
print(f"focos filtrados en Peru: MODIS {len(mod):,} + VIIRS {len(vii):,} = {len(mod) + len(vii):,} "
      f"(MAESTRO P7: 1,295,299)")
print(f"sin departamento asignado (borde/frontera): MODIS {int((mod.dep == '').sum())}, VIIRS {int((vii.dep == '').sum())}")

# ------------------------------------------------------------------ reproduccion de Cusco
c_m, c_v = (mod.dep == "PE-CUS").sum(), (vii.dep == "PE-CUS").sum()
print(f"\n== REPRODUCCION DE CUSCO (limite geoBoundaries, el del equipo es FAO GAUL) ==")
print(f"focos MODIS {c_m:,} (equipo 15,693: {100 * (c_m / 15693 - 1):+.1f} %) | "
      f"VIIRS {c_v:,} (equipo 43,086: {100 * (c_v / 43086 - 1):+.1f} %)")

# ------------------------------------------------------------------ celda-dia por sensor y departamento
KEY = ["dep", "loc", "ci", "cj"]
gm = mod.assign(terra=(mod.satellite == "Terra").astype(int)).groupby(KEY).agg(terra=("terra", "max")).reset_index()
gm["cm"], gm["ct"] = 1, gm.terra
gv = vii.groupby(KEY).size().rename("cv").reset_index()
gv["cv"] = 1
h = gm.merge(gv, on=KEY, how="outer").fillna({"cm": 0, "ct": 0, "cv": 0})
h = h[h.dep != ""]
h["anio"] = h["loc"].dt.year
h["ym"] = h["loc"].dt.to_period("M")
print(f"celda-dias (todo Peru, con departamento): {len(h):,} (MAESTRO P7: ~833 mil)")


def en(df, a, b):
    return df[(df["loc"] >= pd.Timestamp(a)) & (df["loc"] <= pd.Timestamp(b))]


def k_de(df):
    s = en(df, *CAL)
    return s.cm.sum() / s.cv.sum() if s.cv.sum() else np.nan


def anual_ratio(df, k):
    """VIIRS*k / MODIS real por anio de validacion."""
    g = df[df.anio.isin(VAL)].groupby("anio").agg(cm=("cm", "sum"), cv=("cv", "sum"))
    return (g.cv * k / g.cm.replace(0, np.nan))


def mdape_mensual(df, k):
    s = df[df.anio.isin(VAL)].groupby("ym").agg(cm=("cm", "sum"), cv=("cv", "sum"))
    s = s[s.cm >= MIN_MES]
    return (np.abs(s.cv * k - s.cm) / s.cm).median() if len(s) else np.nan, len(s)


def kt_de(df):
    s = en(df, "2003-01-01", "2012-12-31")
    return s.cm.sum() / s.ct.sum() if s.ct.sum() else np.nan


def kt_validacion(df):
    k5 = kt_de(en(df, "2003-01-01", "2007-12-31").assign(anio=0))
    v = en(df, "2008-01-01", "2012-12-31").groupby("ym").agg(cm=("cm", "sum"), ct=("ct", "sum"))
    v = v[v.cm >= MIN_MES]
    return k5, (np.abs(v.ct * k5 - v.cm) / v.cm).median() if len(v) else np.nan, len(v)


k_peru = k_de(h)
k_cus = k_de(h[h.dep == "PE-CUS"])
print(f"\nk sin estratos de altitud, 2013-19: Cusco {k_cus:.3f} | todo Peru {k_peru:.3f}")
print("  (el equipo, con estratos de altitud en Cusco: 0.330 sobre 2500 m y 0.247 debajo; el valor sin "
      "estratos debe quedar entre ambos)")
r = anual_ratio(h[h.dep == "PE-CUS"], k_cus)
print("  Cusco, VIIRS*k/MODIS 2020-24 con su k:", {int(a): round(float(v), 2) for a, v in r.items()},
      "(equipo con estratos: 0.90-1.09)")
m1, n1 = mdape_mensual(h[h.dep == "PE-CUS"], k_cus)
m2, n2 = mdape_mensual(h, k_peru)
m3, _ = mdape_mensual(h, k_cus)
print(f"  error mensual mediano 2020-24: Cusco con su k {100 * m1:.0f} % | TODO Peru con un k unico de Peru {100 * m2:.0f} % "
      f"| TODO Peru con el k de Cusco {100 * m3:.0f} %   (MAESTRO P7: Cusco 10-12 %, Peru 31-33 % con k fijo)")

# ------------------------------------------------------------------ por departamento
rows = []
for dep in sorted(h.dep.unique()):
    s = h[h.dep == dep]
    cal = en(s, *CAL)
    k = k_de(s)
    mc = int((cal.cm > 0).sum())
    vc = int((cal.cv > 0).sum())
    ar = anual_ratio(s, k) if not np.isnan(k) else pd.Series(dtype=float)
    ar_c = anual_ratio(s, k_cus)
    md, nmes = mdape_mensual(s, k) if not np.isnan(k) else (np.nan, 0)
    md_c, _ = mdape_mensual(s, k_cus)
    kt = kt_de(s)
    kt5, ktm, ktn = kt_validacion(s)
    f_m, f_v = int((mod.dep == dep).sum()), int((vii.dep == dep).sum())
    foc = pd.concat([mod[mod.dep == dep][["loc"]], vii[vii.dep == dep][["loc"]]])
    por_mes = foc.groupby(foc["loc"].dt.to_period("M")).size()
    por_anio = foc.groupby(foc["loc"].dt.year).size()
    rows.append({"dep": dep, "nombre": NOMBRE.get(dep, dep), "focos_modis": f_m, "focos_viirs": f_v,
                 "celda_dias": len(s), "cal_cd_modis": mc, "cal_cd_viirs": vc, "k": k,
                 "val_ratio_min": ar.min() if len(ar) else np.nan, "val_ratio_max": ar.max() if len(ar) else np.nan,
                 "mdape_mes_k_propio": md, "meses_medidos": nmes,
                 "val_ratio_min_kCusco": ar_c.min(), "val_ratio_max_kCusco": ar_c.max(), "mdape_mes_kCusco": md_c,
                 "kT": kt, "kT_mdape_mes": ktm, "kT_meses": ktn,
                 "max_focos_mes": int(por_mes.max()), "max_focos_anio": int(por_anio.max())})
t = pd.DataFrame(rows).sort_values("focos_viirs", ascending=False)
OUT.parent.mkdir(parents=True, exist_ok=True)
t.to_csv(OUT, index=False, encoding="utf-8-sig")

pd.set_option("display.width", 250)
print("\n== POR DEPARTAMENTO (ordenado por focos VIIRS) ==")
print(f"{'dep':8}{'focosM':>8}{'focosV':>9}{'cdM-cal':>9}{'cdV-cal':>9}{'k':>7}{'val min-max (k propio)':>24}{'err mes':>9}"
      f"{'val min-max (k Cusco)':>24}{'err mes':>9}{'kT':>7}{'kT err':>8}")
for _, r in t.iterrows():
    print(f"{r.dep:8}{r.focos_modis:8,}{r.focos_viirs:9,}{r.cal_cd_modis:9,}{r.cal_cd_viirs:9,}{r.k:7.3f}"
          f"{'  %5.2f - %5.2f' % (r.val_ratio_min, r.val_ratio_max):>24}{100 * r.mdape_mes_k_propio:8.0f}%"
          f"{'  %5.2f - %5.2f' % (r.val_ratio_min_kCusco, r.val_ratio_max_kCusco):>24}{100 * r.mdape_mes_kCusco:8.0f}%"
          f"{r.kT:7.1f}{100 * r.kT_mdape_mes:7.0f}%")
print(f"\nk de Cusco aplicado a otro departamento: razon anual mediana entre departamentos con muestra suficiente "
      f"(>=300 celda-dias VIIRS en 2013-19):")
ok = t[(t.cal_cd_viirs >= 300)]
print(f"  departamentos con muestra suficiente: {len(ok)} de {len(t)} | k propio entre {ok.k.min():.3f} y {ok.k.max():.3f} "
      f"(Cusco {k_cus:.3f}) | cociente k_max/k_min = {ok.k.max() / ok.k.min():.1f}")
print(f"  departamentos cuya razon anual con el k de Cusco sale de 0.80-1.20 en algun anio: "
      f"{int(((ok.val_ratio_min_kCusco < 0.8) | (ok.val_ratio_max_kCusco > 1.2)).sum())} de {len(ok)}")

# ------------------------------------------------------------------ volumen y limites de la API
print("\n== VOLUMEN Y LIMITES DE LA API (50,000 focos por mapa, 200,000 por CSV, 5 anios por CSV) ==")
tot_f = t.focos_modis.sum() + t.focos_viirs.sum()
print(f"focos totales {tot_f:,} | celda-dias {t.celda_dias.sum():,} | Cusco {t[t.dep == 'PE-CUS'].focos_modis.iloc[0] + t[t.dep == 'PE-CUS'].focos_viirs.iloc[0]:,}")
print("departamentos cuyo MES mas activo supera 50,000 focos (el mapa por mes fallaria):",
      t[t.max_focos_mes > 50000][["dep", "max_focos_mes"]].values.tolist() or "ninguno")
print("departamentos cuyo AÑO mas activo supera 50,000 focos (el mapa por anio fallaria):",
      t[t.max_focos_anio > 50000][["dep", "max_focos_anio"]].values.tolist() or "ninguno")
foc_all = pd.concat([mod[["loc"]], vii[["loc"]]])
pa = foc_all.groupby(foc_all["loc"].dt.year).size()
print(f"todo Peru: focos por anio max {pa.max():,} ({pa.idxmax()}); CSV de 5 anios max ~{int(pa.rolling(5).sum().max()):,}")
print(f"\ntabla completa guardada en {OUT}")
