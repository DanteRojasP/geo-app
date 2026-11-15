"""Donde se va el tiempo de cada consulta (un solo usuario, sin red). Ejecutar desde backend/."""
from __future__ import annotations

import gzip
import json
import time

import duckdb

from firecal.plan import analitica
from firecal.plan.events import plan_dir
from firecal.plan.query import PlanStore
from firecal.settings import get_settings

s = get_settings()
store = PlanStore(s)
aoi = store.resolve_aoi("PE-CUS")
store.monthly(aoi)


def t(fn, n=5):
    best = 1e9
    for _ in range(n):
        t0 = time.perf_counter()
        out = fn()
        best = min(best, time.perf_counter() - t0)
    return best * 1000, out


print("== focos.geojson de un anio (2020) ==")
ms_total, body = t(lambda: store.focos_geojson(aoi, "2020-01", "2020-12"))
ms_json, raw = t(lambda: json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode())
ms_gz, gz = t(lambda: gzip.compress(raw, 9))        # Starlette usa nivel 9 por defecto
ms_gz6, gz6 = t(lambda: gzip.compress(raw, 6))
ms_gz1, gz1 = t(lambda: gzip.compress(raw, 1))
cur = store.cursor()
where = "WHERE TRUE AND (anio * 100 + mes) BETWEEN 202001 AND 202012"
ms_cnt, _ = t(lambda: cur.execute(f"SELECT count(*) FROM fo {where}").fetchall())
ms_sel, rows = t(lambda: cur.execute("SELECT longitude, latitude, fecha_local, hora_utc, sensor, satelite, eq_foco, en_serie, calidad "
                                     f"FROM fo {where} ORDER BY fecha_local, hora_utc").fetchall())
print(f"  funcion completa {ms_total:7.0f} ms = SQL count {ms_cnt:.0f} + SQL select {ms_sel:.0f} + armar {len(rows)} dicts ~{ms_total - ms_cnt - ms_sel:.0f}")
print(f"  + JSON {ms_json:5.0f} ms ({len(raw) / 1024:.0f} KB) + gzip-9 {ms_gz:5.0f} ms ({len(gz) / 1024:.0f} KB) | gzip-6 {ms_gz6:.0f} ms ({len(gz6) / 1024:.0f} KB) | gzip-1 {ms_gz1:.0f} ms ({len(gz1) / 1024:.0f} KB)")
print(f"  TOTAL por visita ~{ms_total + ms_json + ms_gz:.0f} ms de CPU")
en_serie = sum(1 for r in rows if r[7] == 1)
print(f"  focos con peso en la serie: {en_serie} de {len(rows)} ({100 * en_serie / len(rows):.0f} %)")

print("== lo mismo con los datos en una TABLA en memoria (no vistas sobre ~600 Parquet) ==")
con = duckdb.connect()
base = plan_dir(s)
for name, sub in (("cd", "celda_dia"), ("fo", "focos")):
    con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_parquet('{(base / sub / '**' / '*.parquet').as_posix()}', hive_partitioning = true)")
c2 = con.cursor()
ms_cnt2, _ = t(lambda: c2.execute(f"SELECT count(*) FROM fo {where}").fetchall())
ms_sel2, _ = t(lambda: c2.execute("SELECT longitude, latitude, fecha_local, hora_utc, sensor, satelite, eq_foco, en_serie, calidad "
                                  f"FROM fo {where} ORDER BY fecha_local, hora_utc").fetchall())
print(f"  SQL count {ms_cnt2:.0f} ms + select {ms_sel2:.0f} ms  (antes {ms_cnt:.0f} + {ms_sel:.0f})")
n_files = sum(1 for _ in base.rglob("*.parquet"))
print(f"  archivos Parquet que abre cada consulta: {n_files}")

print("== otras consultas (funcion + JSON) ==")
for label, fn in (("calendario (serie en cache)", lambda: store.calendar(aoi, None, None)),
                  ("anomalias 2020-08", lambda: store.anomaly(aoi, "2020-08")),
                  ("focos.geojson mes 2020-08", lambda: store.focos_geojson(aoi, "2020-08", "2020-08")),
                  ("resumen con graficos", lambda: analitica.resumen(store, aoi, graficos=True)),
                  ("analitica acumulado 2019", lambda: analitica.acumulado(store, aoi, 2019)),
                  ("analitica recurrencia", lambda: analitica.recurrencia(store, aoi))):
    ms, body = t(fn, 3)
    raw = json.dumps(body, ensure_ascii=False, default=str).encode()
    ms_gz, gz = t(lambda raw=raw: gzip.compress(raw, 9), 2)
    print(f"  {label:30} {ms:7.0f} ms + gzip {ms_gz:4.0f} ms | {len(raw) / 1024:7.1f} KB -> {len(gz) / 1024:6.1f} KB")

print("== cuantas respuestas distintas existen para Cusco entero ==")
print("  calendario 1 + focos por mes 302 + focos por anio 26 + anomalias 302 + resumen 2 + analiticas ~30, x 2 idiomas = ~1,300")
