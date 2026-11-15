"""Prueba de carga: N personas usando FireCal a la vez, cada una con su propia IP.

Cada persona hace lo que hace la interfaz: abre la pagina (4 llamadas en paralelo), mira varios
meses, abre "En simple" y algunas dibujan un area o descargan el CSV. Igual que api.js, ante un
429/503 espera Retry-After y reintenta una vez.

El servidor debe correr con FIRECAL_TRUST_PROXY=1 para que tome la IP de X-Forwarded-For.
Uso: python carga_usuarios.py <url> <personas> <segundos_de_llegada> [etiqueta]
"""
from __future__ import annotations

import asyncio
import random
import statistics
import sys
import time
from collections import Counter, defaultdict

import httpx

BASE, N, RAMP = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
LABEL = sys.argv[4] if len(sys.argv) > 4 else ""
# "misma-ip": todas las personas salen por la misma IP publica (una sala, una oficina, un wifi).
MISMA_IP = len(sys.argv) > 5 and sys.argv[5] == "misma-ip"
CUS = {"departamento": "PE-CUS"}
lat: dict[str, list[float]] = defaultdict(list)
status: Counter = Counter()
fallos: Counter = Counter()          # lo que la persona ve como error (despues del reintento)
reintentos = 0
carga_inicial: list[float] = []
bytes_total = 0


def nombre(path: str, p: dict) -> str:
    n = path.replace("/api/", "")
    if "bbox" in p:
        n += " (area)"
    elif n == "focos.geojson":
        n += " (anio)" if p["fecha_inicio"] != p["fecha_fin"] else " (mes)"
    return n


async def call(c: httpx.AsyncClient, path: str, **p):
    global reintentos, bytes_total
    key = nombre(path, p)
    t0 = time.perf_counter()
    try:
        r = await c.get(path, params=p)
        if r.status_code in (429, 503):
            status[r.status_code] += 1
            reintentos += 1
            await asyncio.sleep(min(6, float(r.headers.get("Retry-After") or 2)))
            r = await c.get(path, params=p)
        status[r.status_code] += 1
        bytes_total += len(r.content)
        if r.status_code != 200:
            fallos[f"{r.status_code} {key}"] += 1
    except Exception as exc:  # timeout o conexion cortada
        status[type(exc).__name__] += 1
        fallos[f"{type(exc).__name__} {key}"] += 1
    lat[key].append((time.perf_counter() - t0) * 1000)


async def persona(i: int):
    rnd = random.Random(1000 + i)
    await asyncio.sleep(rnd.uniform(0, RAMP))
    ip = "10.9.9.9" if MISMA_IP else f"10.{1 + i // 250}.{i % 250}.{rnd.randint(2, 250)}"
    headers = {"X-Forwarded-For": ip, "Accept-Encoding": "gzip"}
    # Un cliente por persona (su propia IP y conexiones), pero sin crear un contexto TLS cada vez:
    # crear 60 a la vez bloqueaba al generador y falseaba los tiempos.
    # keepalive_expiry < 5 s (el de uvicorn): evita reusar una conexion que el servidor ya cerro;
    # un navegador reintenta solo en ese caso, httpx no.
    async with httpx.AsyncClient(base_url=BASE, timeout=30, headers=headers, verify=False,
                                 trust_env=False, limits=httpx.Limits(keepalive_expiry=1.5)) as c:
        t0 = time.perf_counter()
        await asyncio.gather(call(c, "/api/departamentos.geojson"), call(c, "/api/metadatos"),
                             call(c, "/api/calendario", **CUS),
                             call(c, "/api/focos.geojson", **CUS, fecha_inicio="2025-01", fecha_fin="2025-12"))
        carga_inicial.append((time.perf_counter() - t0) * 1000)
        await asyncio.sleep(rnd.uniform(2, 5))
        for _ in range(4):                                   # mira 4 meses
            m = f"{rnd.randint(2003, 2025)}-{rnd.randint(6, 11):02d}"
            await asyncio.gather(call(c, "/api/focos.geojson", **CUS, fecha_inicio=m, fecha_fin=m),
                                 call(c, "/api/anomalias", **CUS, mes=m))
            await asyncio.sleep(rnd.uniform(2, 4))
        y = rnd.randint(2003, 2024)                          # cambia de anio
        await call(c, "/api/focos.geojson", **CUS, fecha_inicio=f"{y}-01", fecha_fin=f"{y}-12")
        await asyncio.sleep(rnd.uniform(2, 4))
        if rnd.random() < 0.6:                               # abre "En simple"
            await call(c, "/api/resumen", **CUS, graficos="true")
            await asyncio.sleep(rnd.uniform(3, 6))
            if rnd.random() < 0.5:
                await call(c, "/api/analitica/acumulado", **CUS, anio=rnd.randint(2003, 2025))
        if rnd.random() < 0.25:                              # dibuja un area
            w, s = rnd.uniform(-72.6, -71.4), rnd.uniform(-14.2, -13.0)
            bbox = f"{w:.4f},{s:.4f},{w + rnd.uniform(0.3, 0.9):.4f},{s + rnd.uniform(0.3, 0.8):.4f}"
            m = f"{rnd.randint(2013, 2025)}-{rnd.randint(7, 10):02d}"
            await asyncio.gather(call(c, "/api/calendario", bbox=bbox, fecha_inicio=m, fecha_fin=m),
                                 call(c, "/api/focos.geojson", bbox=bbox, fecha_inicio=m, fecha_fin=m))
            await asyncio.sleep(rnd.uniform(2, 4))
        if rnd.random() < 0.15:                              # descarga el CSV de un anio
            await call(c, "/api/hotspots.csv", **CUS, fecha_inicio=f"{y}-01", fecha_fin=f"{y}-12")


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


async def main():
    t0 = time.perf_counter()
    await asyncio.gather(*(persona(i) for i in range(N)))
    dur = time.perf_counter() - t0
    total = sum(len(v) for v in lat.values())
    print(f"\n##### {LABEL} | {N} personas llegando en {RAMP:.0f} s | duracion {dur:.0f} s | {total} llamadas ({total / dur:.1f}/s) | {bytes_total / 1e6:.1f} MB")
    print(f"  abrir la pagina (4 llamadas): mediana {statistics.median(carga_inicial) / 1000:5.1f} s | p95 {pct(carga_inicial, .95) / 1000:5.1f} s | peor {max(carga_inicial) / 1000:5.1f} s")
    print(f"  {'llamada':30} {'n':>4} {'mediana':>9} {'p95':>9} {'peor':>9}  (ms)")
    for k in sorted(lat, key=lambda k: -pct(lat[k], .95)):
        v = lat[k]
        print(f"  {k:30} {len(v):4d} {statistics.median(v):9.0f} {pct(v, .95):9.0f} {max(v):9.0f}")
    print("  respuestas:", dict(status), "| reintentos:", reintentos)
    nf = sum(fallos.values())
    print(f"  ERRORES VISIBLES PARA LA PERSONA: {nf} de {total} ({100 * nf / total:.1f} %)", dict(fallos) if nf else "")


asyncio.run(main())
