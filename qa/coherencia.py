"""Cruce de números entre endpoints, en muchas áreas y rangos al azar (API sin límite de solicitudes, puerto 8100)."""
import csv, io, json, random, math, sys
import httpx

random.seed(20261114)
c = httpx.Client(base_url="http://localhost:8100", timeout=120)
BB = (-73.9932, -15.4575, -70.3461, -11.2108)
COLS = None
problemas = []
def mal(caso, msg, **kw):
    problemas.append({"caso": caso, "msg": msg, **kw})

def ym(y, m): return f"{y}-{m:02d}"

def aois():
    yield ("Cusco", {"departamento": "PE-CUS"})
    for i in range(45):
        w = random.uniform(0.03, 1.4); h = random.uniform(0.03, 1.4)
        x0 = random.uniform(BB[0] - 0.3, BB[2] - w + 0.3); y0 = random.uniform(BB[1] - 0.3, BB[3] - h + 0.3)
        yield (f"bbox{i}", {"bbox": f"{x0:.4f},{y0:.4f},{x0+w:.4f},{y0+h:.4f}"})
    for i in range(15):
        yield (f"punto{i}", {"lat": round(random.uniform(BB[1], BB[3]), 4), "lon": round(random.uniform(BB[0], BB[2]), 4),
                             "radio_km": round(random.uniform(1, 60), 1)})

def rango():
    a = random.randint(2000, 2025); b = random.randint(a, min(2025, a + random.choice([0, 1, 3, 8, 25])))
    ma = random.randint(11 if a == 2000 else 1, 12); mb = random.randint(1, 12)
    if b == a and mb < ma: mb = ma
    return ym(a, ma), ym(b, mb)

n_ok = 0
for nombre, aoi in aois():
    for k in range(2):
        fi, ff = rango()
        caso = f"{nombre} {aoi} {fi}..{ff}"
        r = c.get("/api/calendario", params={**aoi, "fecha_inicio": fi, "fecha_fin": ff})
        if r.status_code != 200:
            if r.status_code not in (404, 422): mal(caso, f"calendario {r.status_code}", detail=r.text[:200])
            # el CSV debe responder igual
            rc = c.get("/api/hotspots.csv", params={**aoi, "fecha_inicio": fi, "fecha_fin": ff})
            if rc.status_code == 200 and int(rc.headers.get("x-row-count", "0")) > 0:
                mal(caso, f"calendario {r.status_code} ({r.json().get('detail')}) pero el CSV trae {rc.headers.get('x-row-count')} focos")
            continue
        cal = r.json()
        celdas = [x for x in cal["celdas"] if not x["sin_dato"]]
        s = round(sum(x["focos_armonizados"] for x in celdas), 2)
        tot = cal["total_focos_armonizados"]
        if abs(s - tot) > 0.05: mal(caso, f"total {tot} ≠ suma de meses {s}")
        # celdas solo dentro del rango
        fuera = [x for x in cal["celdas"] if not (fi <= ym(x["anio"], x["mes"]) <= ff)]
        if fuera: mal(caso, f"{len(fuera)} meses fuera del rango pedido en el calendario")
        # matriz vs celdas
        for x in celdas[:200]:
            i = cal["anios"].index(x["anio"]); j = cal["meses"].index(x["mes"]) if x["mes"] in cal["meses"] else x["mes"] - 1
            mv = cal["matriz_focos_armonizados"][i][j]
            if mv is None or abs(mv - x["focos_armonizados"]) > 0.01:
                mal(caso, f"matriz[{x['anio']}][{x['mes']}]={mv} ≠ celda {x['focos_armonizados']}"); break
        cortes = cal["cortes_color"]
        if cortes != sorted(cortes): mal(caso, f"cortes_color no ordenados {cortes}")
        # CSV
        rc = c.get("/api/hotspots.csv", params={**aoi, "fecha_inicio": fi, "fecha_fin": ff})
        if rc.status_code != 200:
            mal(caso, f"CSV {rc.status_code} con calendario 200 (total {tot})", detail=rc.text[:200]); continue
        txt = rc.content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(txt)))
        if COLS is None: COLS = list(rows[0].keys()) if rows else None
        seq = sum(float(x["eq_foco"]) for x in rows)
        hx = float(rc.headers["x-total-eq-foco"]); hn = int(rc.headers["x-row-count"])
        if hn != len(rows): mal(caso, f"X-Row-Count {hn} ≠ filas {len(rows)}")
        if abs(seq - hx) > 0.05: mal(caso, f"Σ eq_foco del CSV {seq:.2f} ≠ X-Total {hx}")
        if abs(hx - tot) > max(0.05, 0.0006 * len(celdas) * 31 + 0.02): mal(caso, f"total calendario {tot} ≠ total CSV {hx}")
        for x in rows:
            f = x["fecha_local"][:7]
            if not (fi <= f <= ff): mal(caso, f"foco con fecha {x['fecha_local']} fuera del rango"); break
            if "bbox" in aoi:
                w, s_, e, n = map(float, aoi["bbox"].split(","))
                lat, lon = float(x["latitude"]), float(x["longitude"])
                if not (w <= lon <= e and s_ <= lat <= n): mal(caso, f"foco ({lat},{lon}) fuera del rectángulo"); break
        # mapa
        rg = c.get("/api/focos.geojson", params={**aoi, "fecha_inicio": fi, "fecha_fin": ff})
        if rg.status_code == 200:
            g = rg.json(); sg = sum(f["properties"].get("eq_foco", 0) for f in g["features"])
            if abs(sg - hx) > 0.05: mal(caso, f"Σ eq_foco del mapa {sg:.2f} ≠ CSV {hx}")
            if len(g["features"]) != hn: mal(caso, f"mapa {len(g['features'])} puntos ≠ CSV {hn} filas")
        elif not (rg.status_code == 422 and hn > 50000):
            mal(caso, f"mapa {rg.status_code}", detail=rg.text[:200])
        # anomalías de 2 meses al azar
        for x in random.sample(celdas, min(2, len(celdas))):
            ra = c.get("/api/anomalias", params={**aoi, "mes": ym(x["anio"], x["mes"])})
            if ra.status_code != 200: mal(caso, f"anomalias {ym(x['anio'], x['mes'])} {ra.status_code}", detail=ra.text[:200]); continue
            a = ra.json()
            for k2 in ("focos_armonizados", "mediana_hist", "anomalia", "categoria"):
                if a.get(k2) != x.get(k2):
                    mal(caso, f"anomalias {ym(x['anio'], x['mes'])}: {k2} = {a.get(k2)} pero el calendario dice {x.get(k2)}")
        n_ok += 1

json.dump({"problemas": problemas, "casos_ok": n_ok, "cols": COLS}, open("/home/claude/qa/coherencia.json", "w"), ensure_ascii=False, indent=1)
print("casos con datos revisados:", n_ok, "problemas:", len(problemas))
for p in problemas[:40]: print(p)
