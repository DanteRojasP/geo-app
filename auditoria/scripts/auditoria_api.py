"""Auditoria de la interfaz de la API: contrato, cabeceras, tamanos, latencia, errores y limites.

Uso: python auditoria_api.py [url_base]
"""
from __future__ import annotations

import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
cli = httpx.Client(base_url=BASE, timeout=120)
CUS = {"departamento": "PE-CUS"}
BB = "-72.2,-13.6,-71.8,-13.2"


def get(path, wait=True, **p):
    for _ in range(8):
        r = cli.get(path, params=p)
        if wait and r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 1)) + 0.3)
            continue
        return r
    return r


def pausa(s=31):
    """Deja que se recarguen las cubetas del limite antes de una prueba de limites."""
    time.sleep(s)


print("=" * 72, "\n1. CONTRATO (OpenAPI)")
spec = get("/openapi.json").json()
n_typed = 0
for path, ops in sorted(spec["paths"].items()):
    op = ops.get("get", {})
    schema = op.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {})
    typed = "$ref" in schema
    n_typed += typed
    params = [p["name"] for p in op.get("parameters", [])]
    print(f"  {path:34} resp. tipada: {'si' if typed else 'NO':3} | {', '.join(params)}")
print(f"  rutas: {len(spec['paths'])} | con esquema de respuesta: {n_typed} | titulo: {spec['info']['title']} v{spec['info']['version']}")

print("=" * 72, "\n2. CABECERAS, TAMANO Y COMPRESION")
casos = [("/api/calendario", CUS), ("/api/focos.geojson", {**CUS, "fecha_inicio": "2020-01", "fecha_fin": "2020-12"}),
         ("/api/focos.geojson", {**CUS, "fecha_inicio": "2020-08", "fecha_fin": "2020-08"}),
         ("/api/anomalias", {**CUS, "mes": "2020-08"}), ("/api/metadatos", {}), ("/api/departamentos.geojson", {}),
         ("/api/resumen", CUS), ("/api/analitica/recurrencia", CUS)]
for path, p in casos:
    r = cli.get(path, params=p, headers={"Accept-Encoding": "gzip, br"})
    h = r.headers
    raw = len(r.content)
    print(f"  {path:28} {raw / 1024:8.1f} KB | gzip: {h.get('content-encoding', 'NO'):4} | cache-control: {h.get('cache-control', 'NO'):8} | etag: {'si' if 'etag' in h else 'NO'} | {h.get('content-type')}")
idx = cli.get("/", headers={"Accept-Encoding": "gzip"})
import re
assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', idx.text)
for a in assets:
    r = cli.get(a, headers={"Accept-Encoding": "gzip, br"})
    print(f"  {a[:44]:44} {len(r.content) / 1024:8.1f} KB | gzip: {r.headers.get('content-encoding', 'NO'):4} | cache-control: {r.headers.get('cache-control', 'NO')}")
sec = {k: idx.headers.get(k, "NO") for k in ("x-content-type-options", "content-security-policy", "x-frame-options", "strict-transport-security", "referrer-policy")}
print("  cabeceras de seguridad en /:", sec)
pre = cli.options("/api/calendario", headers={"Origin": "https://ejemplo-externo.test", "Access-Control-Request-Method": "GET"})
print("  CORS preflight desde origen externo:", pre.status_code, "| allow-origin:", pre.headers.get("access-control-allow-origin", "NO"))
print("  /docs:", cli.get("/docs").status_code, "| /openapi.json:", cli.get("/openapi.json").status_code, "| /favicon.ico:", cli.get("/favicon.ico").status_code)

pausa()
print("=" * 72, "\n3. LATENCIA (ms del servidor, X-Process-Time-ms; 1.a llamada y mediana de 5 repetidas)")
lat = [("/api/calendario", CUS), ("/api/calendario", {**CUS, "fecha_inicio": "2020-01", "fecha_fin": "2020-12"}),
       ("/api/anomalias", {**CUS, "mes": "2019-08"}), ("/api/focos.geojson", {**CUS, "fecha_inicio": "2019-08", "fecha_fin": "2019-08"}),
       ("/api/focos.geojson", {**CUS, "fecha_inicio": "2019-01", "fecha_fin": "2019-12"}),
       ("/api/metadatos", {}), ("/api/resumen", CUS), ("/api/analitica/estacionalidad", CUS),
       ("/api/analitica/acumulado", {**CUS, "anio": 2019}), ("/api/analitica/recurrencia", {**CUS, "limite": 0}),
       ("/api/calendario", {"bbox": BB}), ("/api/focos.geojson", {"bbox": BB, "fecha_inicio": "2019-01", "fecha_fin": "2019-12"}),
       ("/api/resumen", {"bbox": BB}), ("/api/hotspots.csv", {**CUS, "fecha_inicio": "2000-11", "fecha_fin": "2025-12"})]
for path, p in lat:
    ms = []
    for i in range(6):
        t0 = time.perf_counter()
        r = get(path, **p)
        wall = (time.perf_counter() - t0) * 1000
        ms.append((float(r.headers.get("X-Process-Time-ms", "nan")), wall))
        if "bbox" in p or path.endswith(".csv"):
            time.sleep(6.5)  # respeta 10 pesadas/min
    etiqueta = path + ("?bbox" if "bbox" in p else "") + (" (anio)" if p.get("fecha_inicio", "").endswith("-01") and p.get("fecha_fin", "").endswith("-12") and "2000" not in p.get("fecha_inicio", "") else "")
    print(f"  {etiqueta:38} 1.a {ms[0][0]:8.1f} | mediana {statistics.median(m for m, _ in ms[1:]):8.1f} | total cliente {statistics.median(w for _, w in ms[1:]):8.1f} | {r.status_code}")

pausa()
print("=" * 72, "\n4. VALIDACION Y MENSAJES DE ERROR")
err = [("sin AOI", "/api/calendario", {}),
       ("dos AOI a la vez", "/api/calendario", {**CUS, "bbox": BB}),
       ("parametro mal escrito (departmento)", "/api/calendario", {"departmento": "PE-CUS"}),
       ("departamento en minusculas", "/api/calendario", {"departamento": "pe-cus"}),
       ("bbox con 3 numeros", "/api/calendario", {"bbox": "-72,-13,-71"}),
       ("bbox con texto", "/api/calendario", {"bbox": "a,b,c,d"}),
       ("bbox invertido (oeste > este)", "/api/calendario", {"bbox": "-71.8,-13.6,-72.2,-13.2"}),
       ("bbox demasiado grande", "/api/calendario", {"bbox": "-80,-18,-68,0"}),
       ("lat sin lon", "/api/calendario", {"lat": -13.5}),
       ("punto + radio valido", "/api/calendario", {"lat": -13.5, "lon": -72.0, "radio_km": 20}),
       ("radio negativo", "/api/calendario", {"lat": -13.5, "lon": -72.0, "radio_km": -5}),
       ("radio > maximo", "/api/calendario", {"lat": -13.5, "lon": -72.0, "radio_km": 500}),
       ("fecha con dia (2020-01-15)", "/api/calendario", {**CUS, "fecha_inicio": "2020-01-15", "fecha_fin": "2020-03-20"}),
       ("fecha solo anio (2020)", "/api/calendario", {**CUS, "fecha_inicio": "2020"}),
       ("mes 2020-8 sin cero", "/api/anomalias", {**CUS, "mes": "2020-8"}),
       ("mes faltante", "/api/anomalias", CUS),
       ("mes futuro 2026-03", "/api/anomalias", {**CUS, "mes": "2026-03"}),
       ("anio no numerico", "/api/analitica/acumulado", {**CUS, "anio": "abc"}),
       ("limite fuera de rango", "/api/analitica/recurrencia", {**CUS, "limite": 999999}),
       ("ruta inexistente", "/api/noexiste", {}),
       ("inyeccion en departamento", "/api/calendario", {"departamento": "PE-CUS' OR 1=1 --"}),
       ("inyeccion en bbox", "/api/calendario", {"bbox": "-72.2,-13.6,-71.8,-13.2); DROP TABLE fo; --"})]
for label, path, p in err:
    r = get(path, **p)
    try:
        d = r.json()
        det = d.get("detail") if isinstance(d, dict) else ""
        extra = f" + errors{d['errors']}" if isinstance(d, dict) and d.get("errors") else ""
        txt = (det if isinstance(det, str) else str(det))[:95] + extra[:70] if r.status_code >= 400 else f"OK total={d.get('total_focos_armonizados')}"
    except Exception:
        txt = r.text[:80]
    print(f"  {r.status_code}  {label:36} {txt}")

pausa()
print("=" * 72, "\n5. LIMITES (protocolo de solicitudes)")
codes = [cli.get("/api/metadatos").status_code for _ in range(50)]
print(f"  rafaga de 50 livianas seguidas: {codes.count(200)} x 200, {codes.count(429)} x 429 (limite documentado: rafaga de 40)")
r = cli.get("/api/metadatos")
print("  cabeceras del 429:", {k: r.headers.get(k) for k in ("retry-after", "x-ratelimit-limit", "x-ratelimit-remaining")}, "|", r.json().get("detail") if r.status_code == 429 else r.status_code)
pausa(40)
for label, path, p in (("calendario?bbox (declarada pesada)", "/api/calendario", {"bbox": BB, "fecha_inicio": "2019-08", "fecha_fin": "2019-08"}),
                       ("focos.geojson?bbox", "/api/focos.geojson", {"bbox": BB, "fecha_inicio": "2019-08", "fecha_fin": "2019-08"}),
                       ("analitica/altitud?bbox", "/api/analitica/altitud", {"bbox": BB})):
    codes = [cli.get(path, params=p).status_code for _ in range(9)]
    print(f"  9 seguidas de {label:36}: {codes}")
    pausa(40)
print("  -- concurrencia: 6 consultas pesadas a la vez (turnos: 2 simultaneas, espera 2 s) --")
with ThreadPoolExecutor(6) as ex:
    def una(i):
        with httpx.Client(base_url=BASE, timeout=120) as c:
            t0 = time.perf_counter()
            r = c.get("/api/resumen", params={"bbox": f"-72.{2 + i},-13.6,-71.8,-13.2"})
            return r.status_code, round(time.perf_counter() - t0, 2)
    print("  /api/resumen?bbox x6 simultaneas:", list(ex.map(una, range(6))))
pausa(15)
print("  /health/limits:", cli.get("/health/limits").json())
