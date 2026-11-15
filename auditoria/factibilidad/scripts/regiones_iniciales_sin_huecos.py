"""Regiones mapeadas al inicio (sur del Perú): ¿fallan por sesgo o por muestra? ¿sirve un k regional?

Usa el mismo filtrado y la misma celda-día que factibilidad_regiones.py (Gabriel), pero:
1. Intervalo de confianza (bootstrap de celdas-día dentro de cada año, 2000 réplicas) de la razón anual
   VIIRS*k/MODIS 2020-24 con el k propio: si el intervalo incluye 1, el fallo puede ser ruido de muestra.
2. k regional "sur andino" (Cusco+Puno+Ayacucho+Apurímac, 2013-19) validado en cada departamento.
3. Razón MODIS/VIIRS por año (2013-2024) por departamento: si cae igual en todos, es deriva de MODIS.
Uso: python -I regiones_iniciales.py <firms_raw> <adm1.geojson>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from shapely.geometry import shape
from shapely.ops import unary_union

RAW, LIM = Path(sys.argv[1]), Path(sys.argv[2])
INI = {"PE-CUS": "Cusco", "PE-PUN": "Puno", "PE-AYA": "Ayacucho", "PE-APU": "Apurímac",
       "PE-MDD": "Madre de Dios"}
ANDINO = ["PE-CUS", "PE-PUN", "PE-AYA", "PE-APU"]
RNG = np.random.default_rng(20261115)

feats = json.loads(LIM.read_text(encoding="utf-8-sig"))["features"]
deps = {}
for f in feats:
    iso = f["properties"]["shapeISO"].strip("*")
    if iso in INI:
        deps.setdefault(iso, []).append(shape(f["geometry"]))
deps = {k: unary_union(v) for k, v in deps.items()}


def cargar(patron, viirs):
    fs = sorted(RAW.glob(patron))
    d = pd.concat([pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time",
                                            "satellite", "confidence", "type"],
                               dtype={"confidence": str}) for f in fs], ignore_index=True)
    d = d[d["type"] == 0]
    d = d[d["confidence"].isin(["n", "h"])] if viirs else d[pd.to_numeric(d["confidence"], errors="coerce") >= 30]
    t = pd.to_numeric(d["acq_time"], errors="coerce").fillna(0).astype(int)
    ts = pd.to_datetime(d["acq_date"]) + pd.to_timedelta(t // 100, unit="h") + pd.to_timedelta(t % 100, unit="m")
    d = d.assign(loc=(ts - pd.Timedelta(hours=5)).dt.normalize(),
                 ci=np.floor(d.latitude.to_numpy() / 0.01).astype(int),
                 cj=np.floor(d.longitude.to_numpy() / 0.01).astype(int))
    d["dep"] = ""
    lon, lat = d.longitude.to_numpy(), d.latitude.to_numpy()
    for k, g in deps.items():
        x0, y0, x1, y1 = g.bounds
        c = np.flatnonzero((lon >= x0) & (lon <= x1) & (lat >= y0) & (lat <= y1))
        c = c[shapely.contains_xy(g, lon[c], lat[c])]
        d.iloc[c, d.columns.get_loc("dep")] = k
    return d[d.dep != ""]


mod, vii = cargar("modis_*_Peru.csv", False), cargar("viirs-snpp_*_Peru.csv", True)
KEY = ["dep", "loc", "ci", "cj"]
gm = mod.groupby(KEY).size().rename("cm").reset_index(); gm["cm"] = 1
gv = vii.groupby(KEY).size().rename("cv").reset_index(); gv["cv"] = 1
h = gm.merge(gv, on=KEY, how="outer").fillna({"cm": 0, "cv": 0})
# Días sin ninguna detección VIIRS S-NPP en todo Perú (huecos del satélite, p. ej. 27-jul..10-ago-2022):
# se quitan de MODIS y de VIIRS para comparar lo mismo.
_v = pd.concat([pd.read_csv(f, usecols=["acq_date"]) for f in sorted(RAW.glob("viirs-snpp_*_Peru.csv"))])
_dias = set(pd.to_datetime(_v.acq_date).dt.normalize())
_todos = pd.date_range("2012-01-20", "2025-12-31")
HUECOS = [d for d in _todos if d not in _dias]
h = h[~h["loc"].isin(HUECOS)]
print(f"días sin VIIRS en Perú excluidos: {len(HUECOS)}")
h["anio"] = h["loc"].dt.year
h["ym"] = h["loc"].dt.to_period("M")
cal = h[h.anio.between(2013, 2019)]
val = h[h.anio.between(2020, 2024)]


def k_de(df):
    return df.cm.sum() / df.cv.sum()


def ic_razon(df, k, reps=2000):
    """IC 90 % de VIIRS*k/MODIS por año (bootstrap de celdas-día dentro del año)."""
    out = {}
    for a, g in df.groupby("anio"):
        cm, cv = g.cm.to_numpy(), g.cv.to_numpy()
        # Cada celda-día es solo MODIS, solo VIIRS o ambos: el bootstrap es multinomial sobre 3 conteos.
        n = np.array([((cm == 1) & (cv == 0)).sum(), ((cm == 0) & (cv == 1)).sum(), ((cm == 1) & (cv == 1)).sum()])
        m = RNG.multinomial(n.sum(), n / n.sum(), size=reps)
        r = (m[:, 1] + m[:, 2]) * k / np.maximum(m[:, 0] + m[:, 2], 1)
        out[int(a)] = (round(float(cv.sum() * k / cm.sum()), 2), round(float(np.quantile(r, 0.05)), 2),
                       round(float(np.quantile(r, 0.95)), 2), int(cm.sum()))
    return out


def err_mensual(df, k):
    s = df.groupby("ym").agg(cm=("cm", "sum"), cv=("cv", "sum"))
    s = s[s.cm >= 15]
    return round(float((np.abs(s.cv * k - s.cm) / s.cm).median()) * 100) if len(s) else None


k_andino = k_de(cal[cal.dep.isin(ANDINO)])
print(f"k regional 'sur andino' (Cusco+Puno+Ayacucho+Apurímac, 2013-19): {k_andino:.3f}\n")
for dep, nom in INI.items():
    s_cal, s_val = cal[cal.dep == dep], val[val.dep == dep]
    k = k_de(s_cal)
    ic = ic_razon(s_val, k)
    fuera = [a for a, (r, lo, hi, n) in ic.items() if r < 0.8 or r > 1.2]
    ruido = [a for a in fuera if ic[a][1] <= 1.2 and ic[a][2] >= 0.8]   # el IC toca la banda 0,80-1,20
    print(f"== {nom} ({dep}) | k propio {k:.3f} | celda-días MODIS al calibrar {int(s_cal.cm.sum()):,}")
    print("   razón anual 2020-24 con k propio [IC 90 %] (celda-días MODIS):")
    for a, (r, lo, hi, n) in ic.items():
        marca = "  <- fuera de 0,80-1,20" if (r < 0.8 or r > 1.2) else ""
        print(f"     {a}: {r:.2f} [{lo:.2f}-{hi:.2f}] ({n:,}){marca}")
    print(f"   años fuera de 0,80-1,20 cuyo IC toca la banda (podría ser muestra): {ruido or 'ninguno'}")
    if dep in ANDINO:
        ra = {a: round(float(g.cv.sum() * k_andino / g.cm.sum()), 2) for a, g in s_val.groupby("anio")}
        print(f"   con k sur andino {k_andino:.3f}: razón anual {min(ra.values()):.2f}-{max(ra.values()):.2f} | "
              f"error mensual {err_mensual(s_val, k_andino)} % (con k propio {err_mensual(s_val, k)} %)")
    print()

print("== razón MODIS/VIIRS por año (celda-días), 2013-2024: ¿deriva común de MODIS? ==")
tab = (h[h.anio.between(2013, 2024)].groupby(["dep", "anio"]).agg(cm=("cm", "sum"), cv=("cv", "sum"))
       .assign(r=lambda d: d.cm / d.cv).r.unstack("anio").round(3))
tab.index = [INI[i] for i in tab.index]
print(tab.to_string())
pre, post = tab.loc[:, 2013:2019].mean(axis=1), tab.loc[:, 2020:2024].mean(axis=1)
print("\ncambio medio 2020-24 frente a 2013-19:", {i: f"{100 * (post[i] / pre[i] - 1):+.0f} %" for i in tab.index})
