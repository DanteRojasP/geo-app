"""Costo de servir todo Peru con la arquitectura actual (tablas DuckDB en memoria).

Usa los 1,29 M focos reales de FIRMS con el mismo esquema de tablas que la app (cd = celda-dia,
fo = focos), mas una columna departamento. Los pesos eq_* son sinteticos: para memoria y tiempos
solo importa la forma y el tamano. Uso: python -I capacidad_peru.py <firms_raw> <carpeta_temporal>
"""
from __future__ import annotations

import gc
import json
import os
import re
import sys
import time
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

RAW, TMP = Path(sys.argv[1]), Path(sys.argv[2])
TMP.mkdir(parents=True, exist_ok=True)


def leer(patron, viirs):
    cols = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "type", "frp"]
    d = pd.concat([pd.read_csv(f, usecols=cols, dtype={"confidence": str}) for f in sorted(RAW.glob(patron))], ignore_index=True)
    d = d[d["type"] == 0]
    d = d[d["confidence"].isin(["n", "h"])] if viirs else d[pd.to_numeric(d["confidence"], errors="coerce") >= 30]
    return d.assign(sensor="VIIRS" if viirs else "MODIS")


d = pd.concat([leer("modis_*_Peru.csv", False), leer("viirs-snpp_*_Peru.csv", True)], ignore_index=True)
t = pd.to_numeric(d["acq_time"], errors="coerce").fillna(0).astype(int)
ts = pd.to_datetime(d["acq_date"]) + pd.to_timedelta(t // 100, unit="h") + pd.to_timedelta(t % 100, unit="m")
loc = (ts - pd.Timedelta(hours=5)).dt.normalize()
rng = np.random.default_rng(1)
# Departamento sintetico con el reparto real aproximado (solo para filtrar consultas por departamento).
dep_names = np.array(["PE-%02d" % i for i in range(26)])
dep_w = np.array([22, 20, 15, 13, 10, 9, 8, 6, 5, 5, 4, 3, 3, 3, 2, 2, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1], float); dep_w /= dep_w.sum()
fo = pd.DataFrame({
    "fecha_local": loc.dt.strftime("%Y-%m-%d"), "fecha_utc": d["acq_date"].astype(str), "hora_utc": t.astype(str).str.zfill(4),
    "latitude": d.latitude.round(5), "longitude": d.longitude.round(5),
    "cell_lat": (np.floor(d.latitude / 0.01) * 0.01 + 0.005).round(3), "cell_lon": (np.floor(d.longitude / 0.01) * 0.01 + 0.005).round(3),
    "alt_m": rng.integers(80, 4500, len(d)).astype(float), "sensor": d.sensor, "satelite": d.satellite, "frp": d.frp,
    "brillo_k": 330.0, "confianza": d.confidence, "diurno_nocturno": "D", "fuente_serie": np.where(loc.dt.year >= 2013, "VIIRS*k", "MODIS"),
    "calidad": np.where(loc.dt.year >= 2013, "calibrado", "referencia"), "en_serie": 1, "eq_foco": rng.random(len(d)).round(4),
    "anio": loc.dt.year.astype("int32"), "mes": loc.dt.month.astype("int32"),
    "departamento": rng.choice(dep_names, len(d), p=dep_w)})
fo["n_modis"] = (fo.sensor == "MODIS").astype("int32")
fo["n_viirs"] = (fo.sensor == "VIIRS").astype("int32")
cd = fo.groupby(["departamento", "fecha_local", "cell_lat", "cell_lon"], as_index=False).agg(
    alt_m=("alt_m", "first"), n_modis=("n_modis", "sum"), n_viirs=("n_viirs", "sum"),
    frp_modis=("frp", "sum"), frp_viirs=("frp", "sum"), eq_hotspots=("eq_foco", "sum"), fuente_serie=("fuente_serie", "first"),
    calidad=("calidad", "first"), anio=("anio", "first"), mes=("mes", "first"))
fo = fo.drop(columns=["n_modis", "n_viirs"])
print(f"filas: focos {len(fo):,} | celda-dia {len(cd):,}  (Cusco hoy: 58,779 y 36,260)")

# Parquet particionado por anio/mes, como firecal plan-events
for name, df in (("celda_dia", cd), ("focos", fo)):
    out = TMP / name
    for (a, m), g in df.groupby(["anio", "mes"]):
        p = out / f"anio={a}" / f"mes={m}"
        p.mkdir(parents=True, exist_ok=True)
        g.drop(columns=["anio", "mes"]).to_parquet(p / "part.parquet", index=False)
mb = sum(f.stat().st_size for f in TMP.rglob("*.parquet")) / 1e6
nf = sum(1 for _ in TMP.rglob("*.parquet"))
print(f"Parquet en disco: {mb:.0f} MB en {nf} archivos (Cusco: 3.6 MB en 562)")

del d, t, ts, loc, fo, cd; gc.collect()
t0 = time.perf_counter()
con = duckdb.connect()
for name, sub in (("cd", "celda_dia"), ("fo", "focos")):
    g = (TMP / sub / "**" / "*.parquet").as_posix()
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{g}', hive_partitioning = true)")
carga = time.perf_counter() - t0
mem_db = con.execute("select sum(memory_usage_bytes) from duckdb_memory()").fetchall()[0][0] / 1e6
print(f"cargar tablas al arrancar: {carga:.1f} s (Cusco: 1.6 s) | memoria de DuckDB {mem_db:.0f} MB (Cusco: 20 MB)")

cur = con.cursor()


def t_(sql, params=None, n=3):
    best = 9e9
    for _ in range(n):
        s = time.perf_counter(); r = cur.execute(sql, params or []).fetchall(); best = min(best, time.perf_counter() - s)
    return best * 1000, r


dep = "PE-00"
w = "(anio * 100 + mes) BETWEEN ? AND ?"
ms, r = t_(f"SELECT count(*) FROM fo WHERE departamento = ? AND {w}", [dep, 202008, 202008]); print(f"count focos de 1 depto, 1 mes: {ms:.0f} ms ({r[0][0]:,} filas)")
ms, r = t_("SELECT longitude, latitude, fecha_local, hora_utc, sensor, satelite, eq_foco, en_serie, calidad FROM fo "
           f"WHERE departamento = ? AND {w} ORDER BY fecha_local, hora_utc", [dep, 202001, 202012]); print(f"SELECT focos de 1 depto, 1 anio: {ms:.0f} ms ({len(r):,} filas)  (Cusco hoy: 43 ms para 7,295)")
ms, r = t_("SELECT anio, mes, sum(eq_hotspots), count(*), sum(n_modis), sum(n_viirs) FROM cd WHERE departamento = ? GROUP BY 1, 2", [dep]); print(f"serie mensual de 1 depto (cd): {ms:.0f} ms")
ms, r = t_("SELECT anio, mes, sum(eq_hotspots), count(*), sum(n_modis), sum(n_viirs) FROM cd GROUP BY 1, 2"); print(f"serie mensual de TODO Peru (cd): {ms:.0f} ms")
ms, r = t_("SELECT count(*) FROM fo WHERE longitude BETWEEN -72.6 AND -71.8 AND latitude BETWEEN -13.8 AND -13.2"); print(f"area dibujada (bbox) sobre todo Peru, conteo: {ms:.0f} ms (la app hoy filtra solo por bbox, sin departamento)")
ms, r = t_(f"SELECT longitude, latitude, fecha_local, hora_utc, sensor, satelite, eq_foco, en_serie, calidad FROM fo WHERE {w} ORDER BY fecha_local, hora_utc", [202408, 202408]); print(f"SELECT focos de TODO Peru, 1 mes: {ms:.0f} ms ({len(r):,} filas)")
ms, r = t_(f"SELECT * FROM fo WHERE {w}", [202401, 202412]); print(f"SELECT * de TODO Peru, 1 anio (CSV de un anio): {ms:.0f} ms ({len(r):,} filas; el tope actual es 200,000)")
