"""Simula exactamente lo que hace la interfaz (FireMapApp.jsx) con un área dibujada y el botón ▶.

Al elegir un año (mes = null):   calendario(bbox, año) + focos(bbox, año) + focos(Cusco, año)
Cada tick del ▶ (cada 1,6 s):     calendario(bbox, mes) + focos(bbox, mes) + focos(Cusco, mes) + anomalias(Cusco, mes)
Las 3-4 solicitudes de cada paso salen a la vez (Promise.all / efectos de React en paralelo).
"""
import concurrent.futures as cf, json, sys, threading, time
import httpx

BBOX = "-72.2,-13.4,-71.8,-13.1"   # área de ~1500 km² al norte de la ciudad de Cusco
TICK = 1.6                          # FireMapApp.jsx: setInterval(..., 1600)

def paso(c, pool, etapa, inicio, fin, con_mes):
    reqs = [("cal_area", "/api/calendario", {"bbox": BBOX, "fecha_inicio": inicio, "fecha_fin": fin}),
            ("focos_area", "/api/focos.geojson", {"bbox": BBOX, "fecha_inicio": inicio, "fecha_fin": fin}),
            ("focos_cusco", "/api/focos.geojson", {"departamento": "PE-CUS", "fecha_inicio": inicio, "fecha_fin": fin})]
    if con_mes:
        reqs.append(("anom_cusco", "/api/anomalias", {"departamento": "PE-CUS", "mes": inicio}))
    def one(x):
        name, path, params = x
        t0 = time.time(); r = c.get(path, params=params)
        det = ""
        if r.status_code >= 400:
            try: det = r.json().get("detail", "")
            except Exception: det = r.text[:120]
        return {"etapa": etapa, "req": name, "status": r.status_code, "ms": round((time.time()-t0)*1000),
                "retry_after": r.headers.get("retry-after"), "detail": det}
    return [f.result() for f in [pool.submit(one, x) for x in reqs]]

def correr_anio(port, anio, mes_inicio=1, meses=12, out=None):
    c = httpx.Client(base_url=f"http://localhost:{port}", timeout=60)
    pool = cf.ThreadPoolExecutor(8)
    res = []
    ini = f"{anio}-11" if anio == 2000 else f"{anio}-01"
    res += paso(c, pool, "elegir_año", ini, f"{anio}-12", False)
    time.sleep(2.0)                     # la persona pulsa ▶ unos segundos después
    m = mes_inicio
    for k in range(meses):
        t0 = time.time()
        ym = f"{anio}-{m:02d}"
        res += paso(c, pool, ym, ym, ym, True)
        m = m % 12 + 1
        time.sleep(max(0, TICK - (time.time() - t0)))
    return res

def worker(port, anios, salida):
    for i, a in enumerate(anios):
        if i: time.sleep(35)            # se rellenan los límites antes del siguiente año
        salida[str(a)] = correr_anio(port, a)
        print(f"[{port}] {a} listo", flush=True)

if __name__ == "__main__":
    anios = list(range(2000, 2026))
    ports = [8001, 8002, 8003, 8004, 8005]
    grupos = [anios[i::len(ports)] for i in range(len(ports))]
    salida = {}
    ths = [threading.Thread(target=worker, args=(p, g, salida)) for p, g in zip(ports, grupos)]
    [t.start() for t in ths]; [t.join() for t in ths]
    json.dump(salida, open("/home/claude/qa/play_por_anio.json", "w"), ensure_ascii=False, indent=1)
    print("FIN")
