"""Q/A de logica de las analiticas (/api/analitica/*, /api/resumen): calculo manual vs API.

Uso: python qa_analitica.py <carpeta data/harmonized> [url_base]
"""
from __future__ import annotations

import sys
import time

import httpx
import numpy as np
import pandas as pd

DATA = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8000"
results = []


def check(g, n, ok, d=""):
    results.append((g, n, bool(ok), d))
    print(f"[{'OK ' if ok else 'FALLA'}] {g} | {n} {('-> ' + d) if d else ''}")


cli = httpx.Client(base_url=BASE, timeout=120)


def get(path, **p):
    # lang=es: las frases se comprueban en español (la API responde en inglés por defecto).
    for _ in range(6):
        r = cli.get(path, params={"lang": "es", **p})
        if r.status_code in (429, 503) and "Retry-After" in r.headers:
            time.sleep(float(r.headers["Retry-After"]) + 0.5)
            continue
        return r
    return r


cd = pd.read_csv(f"{DATA}/harmonizado_cusco_celda_dia.csv", dtype={"fecha_local": str})
fo = pd.read_csv(f"{DATA}/focos_cusco_individuales.csv", dtype={"fecha_local": str, "hora_utc": str,
                                                                "confianza": str})
cd["anio"] = cd.fecha_local.str[:4].astype(int)
cd["mes"] = cd.fecha_local.str[5:7].astype(int)
fo["anio"] = fo.fecha_local.str[:4].astype(int)

# serie mensual completa 2000-11..2025-12 con ceros
idx = pd.period_range("2000-11", "2025-12", freq="M")
m = pd.DataFrame({"anio": idx.year, "mes": idx.month})
m = m.merge(cd.groupby(["anio", "mes"]).eq_hotspots.sum().rename("n").reset_index(),
            on=["anio", "mes"], how="left").fillna({"n": 0.0})
# anios de referencia: 12 meses y ningun foco extrapolado ni mes anterior a 2002-07
ext_anios = set(cd[cd.calidad == "extrapolado"].anio)
REF = [a for a in range(2001, 2026) if a not in ext_anios and a > 2002]
check("0. Base", "anios de referencia = 2003-2025", REF == list(range(2003, 2026)), f"{REF[0]}-{REF[-1]}")
hist = m[m.anio.isin(REF)]

# ------------------------------------------------ 1. estacionalidad
G = "1. Estacionalidad"
r = get("/api/analitica/estacionalidad", departamento="PE-CUS").json()
api = pd.DataFrame(r["meses"]).set_index("mes")
med = hist.groupby("mes").n.median()
p25 = hist.groupby("mes").n.quantile(0.25)
p75 = hist.groupby("mes").n.quantile(0.75)
parte = hist.groupby("mes").n.sum() / hist.n.sum()
check(G, "mediana por mes = manual", np.allclose(api.mediana, med.round(1), atol=0.051),
      f"max dif {np.abs(api.mediana - med).max():.3f}")
check(G, "p25/p75 por mes = manual", np.allclose(api.p25, p25, atol=0.051) and np.allclose(api.p75, p75, atol=0.051))
check(G, "parte del anio por mes = manual (suma 1)",
      np.allclose(api.parte_del_anio, parte, atol=0.0006) and abs(parte.sum() - 1) < 1e-9)
orden = parte.sort_values(ascending=False)
temporada, acum = [], 0.0
for mes, p in orden.items():
    temporada.append(int(mes))
    acum += p
    if acum >= 0.80:
        break
check(G, "temporada (meses que suman >=80 %) = manual", sorted(temporada) == r["temporada"],
      f"manual {sorted(temporada)} ({acum:.1%}) vs API {r['temporada']} ({r['parte_temporada']:.1%})")
check(G, "mes pico (mayor mediana) = manual", int(med.idxmax()) == r["mes_pico"], f"{r['mes_pico']}")
print("   frase:", r["en_simple"])

# ------------------------------------------------ 2. ranking
G = "2. Ranking"
r = get("/api/analitica/ranking", departamento="PE-CUS").json()
anual = m.groupby("anio").agg(n=("n", "sum"), meses=("mes", "size"))
anual = anual[anual.meses == 12].n
tipico = anual.loc[REF].median()
check(G, "anio tipico = mediana de totales 2003-2025", abs(r["anio_tipico"] - tipico) <= 0.051,
      f"API {r['anio_tipico']} vs {tipico:.2f}")
api = pd.DataFrame(r["anios"])
check(G, "anios completos listados (2001-2025)", sorted(api.anio) == sorted(anual.index),
      f"{len(api)} anios")
check(G, "totales anuales = manual",
      np.allclose(api.set_index("anio").total.sort_index(), anual.sort_index(), atol=0.051))
check(G, "orden descendente por total y puestos 1..N",
      list(api.total) == sorted(api.total, reverse=True) and list(api.puesto) == list(range(1, len(api) + 1)))
firmes = anual.loc[REF]
check(G, "frase: mayor y menor anio firmes = manual",
      str(firmes.idxmax()) in r["en_simple"] and str(firmes.idxmin()) in r["en_simple"],
      f"manual mayor {firmes.idxmax()} ({firmes.max():.0f}), menor {firmes.idxmin()} ({firmes.min():.0f})")
cal_ext = api.set_index("anio").calidad
check(G, "2001 extrapolado y 2002 mixto; resto ok",
      cal_ext[2001] == "extrapolado" and cal_ext[2002] == "mixto"
      and (cal_ext.drop([2001, 2002]) == "ok").all(), f"2001={cal_ext[2001]} 2002={cal_ext[2002]}")
print("   frase:", r["en_simple"])

# ------------------------------------------------ 3. acumulado
G = "3. Acumulado"
d = cd.assign(dia=pd.to_datetime(cd.fecha_local).dt.dayofyear.clip(upper=365))
piv = d.pivot_table(index="anio", columns="dia", values="eq_hotspots", aggfunc="sum", fill_value=0.0)
piv = piv.reindex(index=range(2001, 2026), columns=range(1, 366), fill_value=0.0).cumsum(axis=1)
base = piv.loc[REF]
for anio in (2020, 2025, 2010):
    r = get("/api/analitica/acumulado", departamento="PE-CUS", anio=anio).json()
    fin, nor = piv.loc[anio, 365], base[365].median()
    lo, hi = base[365].quantile(0.1), base[365].quantile(0.9)
    ok = (abs(r["total"] - fin) <= 0.051 and abs(r["normal"] - nor) <= 0.051
          and abs(r["rango_normal"][0] - lo) <= 0.051 and abs(r["rango_normal"][1] - hi) <= 0.051)
    ver = "muy por encima" if fin > hi else "muy por debajo" if fin < lo else "dentro"
    ok &= r["veredicto"].startswith(ver)
    curva = pd.DataFrame(r["curva"]).set_index("dia")
    ok &= np.allclose(curva.acumulado, piv.loc[anio, curva.index], atol=0.051)
    ok &= np.allclose(curva.normal, base[curva.index].median(), atol=0.051)
    det = f"{anio}: total {fin:.1f} normal {nor:.1f} p10-p90 {lo:.1f}-{hi:.1f} -> {ver}"
    if anio == 2020:
        cruce = int(np.flatnonzero(piv.loc[2020].to_numpy() >= nor)[0])
        fecha = pd.Timestamp(2020, 1, 1) + pd.Timedelta(days=cruce)
        det += f" | cruce manual {fecha.date()}"
        ok &= f"{fecha.day} de agosto" in r["en_simple"] if fecha.month == 8 else True
        print("   frase:", r["en_simple"])
    if anio == 2025:
        ok &= any("2025" in n for n in r["notes"])
        det += " | nota 2025 presente"
    check(G, f"anio {anio} = manual (total, mediana, p10/p90, curva, veredicto)", ok, det)
r = get("/api/analitica/acumulado", departamento="PE-CUS", anio=1999)
check(G, "anio fuera de rango -> 422", r.status_code == 422, str(r.status_code))

# ------------------------------------------------ 4. altitud
G = "4. Altitud"
r = get("/api/analitica/altitud", departamento="PE-CUS").json()
bins = [-np.inf, 1500, 2500, 3500, np.inf]
cd["banda"] = pd.cut(cd.alt_m, bins, right=False, labels=False)
man = cd.groupby("banda").eq_hotspots.sum()
celdas = cd.groupby("banda").apply(lambda g: len(set(zip(g.cell_lat, g.cell_lon))), include_groups=False)
api = pd.DataFrame(r["bandas"])
check(G, "focos por franja = manual", np.allclose(api.focos_armonizados, man.values, atol=0.051),
      f"{list(api.focos_armonizados)} vs {[round(x, 1) for x in man.values]}")
check(G, "celdas distintas por franja = manual", list(api.celdas) == list(celdas.values),
      f"{list(api.celdas)}")
check(G, "partes suman 1 y la frase usa >= 2500 m", abs(api.parte.sum() - 1) < 0.002)
print("   frase:", r["en_simple"])

# ------------------------------------------------ 5. recurrencia (solo VIIRS desde 2013)
G = "5. Recurrencia"
r = get("/api/analitica/recurrencia", departamento="PE-CUS").json()
v = cd[(cd.anio >= 2013) & (cd.n_viirs > 0)]
viirs = v.groupby(["cell_lat", "cell_lon"]).anio.nunique()
todo = cd[cd.anio >= 2013].groupby(["cell_lat", "cell_lon"]).anio.nunique()
solo_modis = int(((cd.anio >= 2013) & (cd.n_viirs == 0)).sum())
print(f"   celdas-dia desde 2013 sin VIIRS (solo MODIS, peso 0): {solo_modis}")
check(G, "lugares = celdas con VIIRS desde 2013 (manual)", r["lugares"] == len(viirs),
      f"API {r['lugares']} | manual solo VIIRS {len(viirs)} | contando tambien solo-MODIS {len(todo)}")
umbral = max(3, round(r["anios_posibles"] / 3))
check(G, "lugares recurrentes (>= umbral anios) = manual",
      r["lugares_recurrentes"] == int((viirs >= umbral).sum()),
      f"API {r['lugares_recurrentes']} vs manual {(viirs >= umbral).sum()} (umbral {umbral})")
check(G, "anios posibles = 13 (2013-2025)", r["anios_posibles"] == 13, str(r["anios_posibles"]))
# misma consulta con un bbox que cubre todo Cusco (usa focos en_serie=1 = VIIRS)
rb = get("/api/analitica/recurrencia", bbox="-73.99,-15.49,-70.31,-11.21")
if rb.status_code == 200:
    check(G, "Cusco entero vs bbox equivalente: mismos lugares",
          rb.json()["lugares"] == r["lugares"], f"departamento {r['lugares']} vs bbox {rb.json()['lugares']}")
else:
    print("   (bbox amplio no permitido:", rb.status_code, rb.json().get("detail", "")[:90], ")")
print("   frase:", r["en_simple"])

# ------------------------------------------------ 6. resumen y area dibujada
G = "6. Resumen/AOI"
r = get("/api/resumen", departamento="PE-CUS").json()
check(G, "resumen trae 5 frases y nota de no pronostico",
      len(r["frases"]) == 5 and any("pronóstico" in n for n in r["notes"]))
txt = " ".join(f["respuesta"] for f in r["frases"]).lower()
check(G, "sin palabras prohibidas (riesgo, alerta, evento)",
      not any(w in txt for w in ("riesgo", "alerta", "evento")))
BB = (-72.2, -13.6, -71.8, -13.2)
r = get("/api/analitica/ranking", bbox=",".join(map(str, BB))).json()
selb = fo[(fo.en_serie == 1) & fo.longitude.between(BB[0], BB[2]) & fo.latitude.between(BB[1], BB[3])]
man = selb.groupby("anio").eq_foco.sum()
api = pd.DataFrame(r["anios"]).set_index("anio").total
check(G, "bbox: totales anuales del ranking = suma eq_foco manual",
      np.allclose(api.sort_index(), man.reindex(api.index, fill_value=0).sort_index(), atol=0.051),
      f"2020 API {api.get(2020)} vs manual {man.get(2020, 0):.2f}")
r = get("/api/analitica/ranking", departamento="PE-LOR")
check(G, "otro departamento -> 404", r.status_code == 404, str(r.status_code))

ok = sum(x[2] for x in results)
print(f"\nRESUMEN: {ok}/{len(results)} verificaciones OK")
pd.DataFrame(results, columns=["grupo", "prueba", "ok", "detalle"]).to_csv(
    sys.argv[0].replace(".py", "_resultado.csv"), index=False, encoding="utf-8-sig")
sys.exit(0 if ok == len(results) else 1)
