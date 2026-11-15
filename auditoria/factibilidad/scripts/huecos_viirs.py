"""Huecos de VIIRS S-NPP y su efecto en la serie armonizada de Cusco.

1. Días de junio a noviembre sin ninguna detección VIIRS S-NPP en todo Perú (el satélite no entregó datos).
2. Celdas-día MODIS de Cusco en esos días: hoy pesan 0 en la serie (desde 2013 solo cuenta VIIRS*k).
   Se comparan con lo que muestra la app (data/harmonized/harmonizado_cusco_celda_dia.csv).

Uso (desde la raíz del repo): python -I huecos_viirs.py <firms_raw> <adm1.geojson>
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
SERIE = Path("data/harmonized/harmonizado_cusco_celda_dia.csv")

v = pd.concat([pd.read_csv(f, usecols=["acq_date"]) for f in sorted(RAW.glob("viirs-snpp_*_Peru.csv"))])
por_dia = pd.to_datetime(v.acq_date).dt.normalize().value_counts()
huecos = {d for d in pd.date_range("2013-01-01", "2025-12-31") if por_dia.get(d, 0) == 0}
print("== días de junio a noviembre sin VIIRS S-NPP en todo Perú ==")
for y in range(2013, 2026):
    n = sorted(d for d in huecos if d.year == y and 6 <= d.month <= 11)
    tramos = []
    for d in n:
        if tramos and (d - tramos[-1][1]).days == 1:
            tramos[-1][1] = d
        else:
            tramos.append([d, d])
    largos = [f"{a:%d-%m}..{b:%d-%m} ({(b - a).days + 1} d)" for a, b in tramos if (b - a).days >= 2]
    print(f"{y}: {len(n):3d} días | tramos de 3+ días: {largos or '-'}")

feats = json.loads(LIM.read_text(encoding="utf-8-sig"))["features"]
cus = unary_union([shape(f["geometry"]) for f in feats if f["properties"]["shapeISO"].strip("*") == "PE-CUS"])
m = pd.concat([pd.read_csv(f, usecols=["latitude", "longitude", "acq_date", "acq_time", "confidence", "type"])
               for f in sorted(RAW.glob("modis_20[12]*_Peru.csv"))])
m = m[(m["type"] == 0) & (pd.to_numeric(m.confidence, errors="coerce") >= 30)]
m = m[shapely.contains_xy(cus, m.longitude.to_numpy(), m.latitude.to_numpy())]
t = m.acq_time.astype(int)
m["loc"] = (pd.to_datetime(m.acq_date) + pd.to_timedelta(t // 100, unit="h")
            + pd.to_timedelta(t % 100, unit="m") - pd.Timedelta(hours=5)).dt.normalize()
m = m[m["loc"].isin(huecos)]
cd = m.assign(ci=np.floor(m.latitude / 0.01), cj=np.floor(m.longitude / 0.01)).drop_duplicates(["loc", "ci", "cj"])

serie = pd.read_csv(SERIE, usecols=["fecha_local", "eq_hotspots"], dtype={"fecha_local": str})
serie["f"] = pd.to_datetime(serie.fecha_local.str[:10])
en_huecos = serie[serie.f.isin(huecos)]
print(f"\n== Cusco ==\nceldas-día de la serie en días sin VIIRS: {len(en_huecos)} "
      f"(focos armonizados {en_huecos.eq_hotspots.sum():.1f}): esos días cuentan 0")
print(f"celdas-día MODIS de Cusco en esos días (límite geoBoundaries): {len(cd)}")
tot = serie.groupby(serie.fecha_local.str[:7]).eq_hotspots.sum()
for ym, n in cd.groupby(cd["loc"].dt.strftime("%Y-%m")).size().items():
    app = tot.get(ym, 0.0)
    print(f"  {ym}: la app muestra {app:.0f}; con MODIS en los días sin VIIRS serían ~{app + n:.0f} "
          f"({100 * n / max(app, 1):+.0f} %)")
