"""Recorrido funcional de la interfaz con Chrome sin ventana (protocolo DevTools).

Abre la app, pulsa los controles como un usuario, guarda capturas y registra cada llamada a la
API (ruta, estado, ms) y los errores de consola.
Uso: python ui_recorrido.py <chrome.exe> <carpeta_salida> [url]
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from websockets.sync.client import connect

CHROME, OUT = sys.argv[1], Path(sys.argv[2])
URL = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000/"
PORT = 9333
OUT.mkdir(parents=True, exist_ok=True)
profile = OUT / "perfil_chrome"

proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}",
                         f"--user-data-dir={profile}", "--window-size=1440,900", "--hide-scrollbars",
                         "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--no-first-run",
                         "--remote-allow-origins=*", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
            break
        except Exception:
            time.sleep(0.5)
    page = next(t for t in tabs if t["type"] == "page")
    ws = connect(page["webSocketDebuggerUrl"], max_size=None)
    seq = 0
    reqs: dict[str, dict] = {}
    api_log: list[dict] = []
    errors: list[str] = []
    paso = "inicio"

    def handle(msg):
        m, p = msg.get("method"), msg.get("params", {})
        if m == "Network.requestWillBeSent":
            reqs[p["requestId"]] = {"url": p["request"]["url"], "paso": paso}
        elif m == "Network.responseReceived":
            r = reqs.get(p["requestId"])
            if r and "/api/" in r["url"] and urlsplit(r["url"]).netloc.startswith("127.0.0.1"):
                h = {k.lower(): v for k, v in p["response"]["headers"].items()}
                u = urlsplit(r["url"])
                api_log.append({"paso": r["paso"], "ruta": u.path, "query": u.query,
                                "estado": p["response"]["status"], "ms": h.get("x-process-time-ms"),
                                "restantes": h.get("x-ratelimit-remaining")})
        elif m == "Runtime.exceptionThrown":
            errors.append(f"[{paso}] excepcion: " + p["exceptionDetails"].get("text", "")[:200])
        elif m == "Log.entryAdded" and p["entry"]["level"] == "error":
            errors.append(f"[{paso}] {p['entry'].get('text', '')[:160]} {p['entry'].get('url', '')[:90]}")

    def cmd(method, **params):
        global seq
        seq += 1
        ws.send(json.dumps({"id": seq, "method": method, "params": params}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == seq:
                return msg.get("result", {})
            handle(msg)

    def wait(seconds):
        end = time.time() + seconds
        while time.time() < end:
            try:
                handle(json.loads(ws.recv(timeout=0.25)))
            except TimeoutError:
                pass

    def js(expr):
        r = cmd("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def shot(name):
        data = cmd("Page.captureScreenshot", format="png")["data"]
        (OUT / f"{name}.png").write_bytes(base64.b64decode(data))

    def step(name):
        global paso
        paso = name
        print(">>", name)

    def click(selector_js, espera=2.5):
        ok = js(f"(() => {{ const el = {selector_js}; if (!el) return false; el.click(); return true }})()")
        wait(espera)
        return ok

    for d in ("Page", "Network", "Runtime", "Log"):
        cmd(f"{d}.enable")

    step("01_carga")
    cmd("Page.navigate", url=URL)
    wait(12)
    shot("01_carga")
    print("   titulo:", js("document.title"), "| canvas mapa:", js("!!document.querySelector('.fw-map canvas')"),
          "| celdas calendario:", js("document.querySelectorAll('.fc-calendar td').length"))
    print("   tema del panel (fondo/color):", js("(() => { const s = getComputedStyle(document.querySelector('.fw-summary')); return s.backgroundColor + ' / ' + s.color })()"))
    print("   fuente minima visible (px):", js("Math.min(...[...document.querySelectorAll('body *')].filter(e => e.childNodes.length && [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && e.getClientRects().length).map(e => parseFloat(getComputedStyle(e).fontSize)))"))
    print("   elementos de texto visibles < 11 px:", js("(() => { const els = [...document.querySelectorAll('body *')].filter(e => [...e.childNodes].some(n => n.nodeType === 3 && n.textContent.trim()) && e.getClientRects().length); return els.filter(e => parseFloat(getComputedStyle(e).fontSize) < 11).length + ' de ' + els.length })()"))
    print("   botones sin nombre accesible:", js("[...document.querySelectorAll('button')].filter(b => !b.textContent.trim() && !b.title && !b.getAttribute('aria-label')).length"),
          "| celdas clicables alcanzables con teclado:", js("[...document.querySelectorAll('.fc-calendar td')].filter(t => t.tabIndex >= 0).length"))

    step("02_mes_ago2020")
    print("   clic celda:", click("[...document.querySelectorAll('.fc-calendar td')].find(t => (t.title || '').startsWith('Ago 2020'))", 4))
    shot("02_mes_ago2020")
    print("   panel:", js("document.querySelector('.fw-summary')?.innerText.replace(/\\n+/g, ' | ').slice(0, 330)"))

    step("03_modo_anomalia")
    click("[...document.querySelectorAll('.fc-toggle button')].find(b => b.textContent.trim() === 'Anomalía')", 1.5)
    shot("03_modo_anomalia")

    step("04_capa_puntos")
    click("document.querySelector('.fc-toggle button[title=\"Cerrar calendario\"]')", 1)
    click("[...document.querySelectorAll('.fw-layer-button')].find(b => b.textContent.trim() === 'Focos')", 3)
    shot("04_capa_puntos")

    step("05_capa_limite")
    click("[...document.querySelectorAll('.fw-layer-button')].find(b => b.textContent.trim() === 'Límite')", 2.5)
    shot("05_capa_limite")
    click("[...document.querySelectorAll('.fw-layer-button')].find(b => b.textContent.trim() === 'Densidad')", 1)

    step("06_en_simple")
    click("document.querySelector('.fw-rail button[title^=\"El fuego en simple\"]')", 6)
    shot("06_en_simple")
    print("   frases:", js("document.querySelectorAll('.fs-frases dd').length"), "| graficos:", js("document.querySelectorAll('.fs-svg svg').length"))
    js("document.querySelector('.fs-body')?.scrollTo(0, 99999)")
    wait(1)
    shot("06b_en_simple_abajo")
    click("document.querySelector('.fs-head button')", 1)

    step("07_area")
    click("document.querySelector('.fw-rail button[title=\"Seleccionar área\"]')", 1)
    x0, y0, x1, y1 = 820, 300, 930, 400
    print("   elemento bajo el cursor:", js(f"document.elementFromPoint({x0},{y0})?.tagName + '.' + document.elementFromPoint({x0},{y0})?.className"))
    cmd("Input.dispatchMouseEvent", type="mousePressed", x=x0, y=y0, button="left", buttons=1, clickCount=1)
    for i in range(1, 9):
        cmd("Input.dispatchMouseEvent", type="mouseMoved", x=x0 + (x1 - x0) * i / 8, y=y0 + (y1 - y0) * i / 8, button="left", buttons=1)
    cmd("Input.dispatchMouseEvent", type="mouseReleased", x=x1, y=y1, button="left", buttons=0, clickCount=1)
    wait(6)
    shot("07_area")
    print("   tarjeta del area:", js("document.querySelector('.fw-selection-card')?.innerText.replace(/\\n+/g, ' | ').slice(0, 300)"))

    step("08_en_simple_area")
    click("document.querySelector('.fw-rail button[title^=\"El fuego en simple\"]')", 9)
    shot("08_en_simple_area")
    print("   error en panel:", js("document.querySelector('.fs-error')?.innerText"), "| frases:", js("document.querySelectorAll('.fs-frases dd').length"))
    click("document.querySelector('.fs-head button')", 1)

    step("09_reproducir_con_area")
    click("document.querySelector('.fw-play')", 0)
    wait(20)
    shot("09_reproducir_con_area")
    print("   error visible:", js("[...document.querySelectorAll('.fw-error')].map(e => e.innerText).join(' || ')"))
    click("document.querySelector('.fw-play')", 1)
    click("document.querySelector('.fw-selection-head button')", 1)

    step("10_movil")
    cmd("Emulation.setDeviceMetricsOverride", width=390, height=844, deviceScaleFactor=2, mobile=True)
    cmd("Page.reload")
    wait(12)
    shot("10_movil")
    print("   desborde horizontal:", js("document.documentElement.scrollWidth > innerWidth"),
          "| botones < 44 px:", js("(() => { const b = [...document.querySelectorAll('button')].filter(e => e.getClientRects().length); return b.filter(e => { const r = e.getBoundingClientRect(); return r.width < 44 || r.height < 44 }).length + ' de ' + b.length })()"))
    click("document.querySelector('.fw-rail button[title=\"Calendario\"]')", 2)
    shot("10b_movil_calendario")

    print("\n=== LLAMADAS A LA API POR PASO ===")
    por = {}
    for a in api_log:
        por.setdefault(a["paso"], []).append(a)
    for p, lst in por.items():
        est = {}
        for a in lst:
            est[a["estado"]] = est.get(a["estado"], 0) + 1
        print(f"{p}: {len(lst)} llamadas, estados {est}")
        for a in lst[:14]:
            print(f"    {a['estado']} {a['ms'] or '-':>7} ms  {a['ruta']}?{a['query'][:70]}")
        if len(lst) > 14:
            print(f"    ... {len(lst) - 14} mas")
    print("\n=== ERRORES DE CONSOLA ===")
    for e in dict.fromkeys(errors):
        print("  ", e)
    print("total:", len(errors))
    (OUT / "api_log.json").write_text(json.dumps(api_log, indent=1), encoding="utf-8")
    ws.close()
finally:
    proc.terminate()
