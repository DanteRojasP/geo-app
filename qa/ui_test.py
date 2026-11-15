"""Prueba de la interfaz real (main) en Chrome sin pantalla contra la API local con límites activos (8200)."""
import json, re, time, os
from playwright.sync_api import sync_playwright

URL = "http://localhost:8200/"
OUT = "/home/claude/qa/ui"
os.makedirs(OUT, exist_ok=True)
log = {"console_errors": [], "page_errors": [], "api_fallidas": [], "pasos": []}

def paso(nombre, **kw):
    log["pasos"].append({"paso": nombre, **kw}); print("·", nombre, kw if kw else "")

def banner(page):
    els = page.locator(".fw-error, .fc-notice")
    return [els.nth(i).inner_text() for i in range(els.count())]

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True,
                          args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True, locale="es-PE")
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and log["console_errors"].append(m.text[:300]))
    page.on("pageerror", lambda e: log["page_errors"].append(str(e)[:300]))
    page.on("response", lambda r: ("localhost" in r.url and r.status >= 400) and log["api_fallidas"].append(f"{r.status} {r.url.replace('http://localhost:8200','')[:160]}"))

    t0 = time.time(); page.goto(URL, wait_until="domcontentloaded"); page.wait_for_timeout(7000)
    paso("carga inicial", segundos=round(time.time() - t0, 1), banners=banner(page))
    page.screenshot(path=f"{OUT}/01_inicio.png")
    body = page.inner_text("body")
    paso("textos clave", firms=("FIRMS" in body), focos_armonizados=("focos armonizados" in body.lower()),
         mapa_canvas=page.locator("canvas.maplibregl-canvas").count())

    # Año 2000: meses sin datos y ▶
    for _ in range(30):
        btn = page.get_by_title("Año anterior")
        if btn.is_disabled(): break
        btn.click(); page.wait_for_timeout(250)
    page.wait_for_timeout(1500)
    meses = page.locator("button[title='Sin dato']")
    paso("año 2000", meses_deshabilitados=meses.count(), banners=banner(page))
    page.get_by_title("Recorrer los meses del año").click(); page.wait_for_timeout(9000)
    paso("año 2000 con ▶ (9 s)", banners=banner(page))
    page.screenshot(path=f"{OUT}/02_anio2000_play.png")
    page.get_by_title("Pausar").click(); page.wait_for_timeout(500)

    # Ir a 2024, descargar CSV de Cusco
    for _ in range(24): page.get_by_title("Año siguiente").click(); page.wait_for_timeout(150)
    page.wait_for_timeout(2500)
    paso("año 2024", banners=banner(page), texto_barra=page.locator(".fw-time-info").inner_text().replace("\n", " "))
    try:
        with page.expect_download(timeout=20000) as dl:
            page.locator("button:has-text('CSV')").first.click()
        d = dl.value; path = f"{OUT}/{d.suggested_filename}"; d.save_as(path)
        lines = open(path, encoding="utf-8-sig").read().splitlines()
        paso("CSV de Cusco", archivo=d.suggested_filename, filas=len(lines) - 1, aviso=banner(page))
    except Exception as e:
        paso("CSV de Cusco FALLÓ", error=str(e)[:200])

    # Calendario: modo anomalía
    try:
        page.locator("button:has-text('Anomalía')").first.click(); page.wait_for_timeout(1200)
        page.screenshot(path=f"{OUT}/03_calendario_anomalia.png"); paso("modo anomalía", banners=banner(page))
        page.locator("button:has-text('Focos')").first.click()
    except Exception as e:
        paso("modo anomalía FALLÓ", error=str(e)[:200])

    # Panel "En simple"
    page.get_by_title("El fuego en simple: respuestas y gráficos").click(); page.wait_for_timeout(5000)
    panel = page.locator("text=en simple").first
    page.screenshot(path=f"{OUT}/04_en_simple.png")
    txt = page.inner_text("body")
    paso("panel En simple", tiene_88=("88 %" in txt), botones_png=page.locator("button:has-text('PNG')").count(), banners=banner(page))
    sel = page.locator("select")
    paso("selectores en panel", n=sel.count(), opciones=[sel.nth(i).locator("option").all_inner_texts()[:3] + ['…'] + sel.nth(i).locator("option").all_inner_texts()[-2:] for i in range(sel.count())])
    try:
        with page.expect_download(timeout=10000) as dl:
            page.locator("button:has-text('PNG')").first.click()
        paso("descarga PNG", archivo=dl.value.suggested_filename)
    except Exception as e:
        paso("descarga PNG FALLÓ", error=str(e)[:200])
    page.get_by_title("El fuego en simple: respuestas y gráficos").click(); page.wait_for_timeout(500)

    # Selección de área sobre el mapa + ▶
    page.get_by_title("Seleccionar área").click(); page.wait_for_timeout(600)
    cv = page.locator("canvas.maplibregl-canvas").bounding_box()
    if cv:
        x0, y0 = cv["x"] + cv["width"] * 0.45, cv["y"] + cv["height"] * 0.40
        page.mouse.move(x0, y0); page.mouse.down(); page.mouse.move(x0 + 120, y0 + 90, steps=8); page.mouse.up()
        page.wait_for_timeout(3500)
        page.screenshot(path=f"{OUT}/05_area.png")
        sel_txt = page.locator(".fw-selection-grid, .fw-selection-actions").all_inner_texts()
        paso("área dibujada", panel=" | ".join(t.replace("\n", " ") for t in sel_txt)[:300], banners=banner(page))
        page.get_by_title("Recorrer los meses del año").click()
        visto = []
        for k in range(14):
            page.wait_for_timeout(1600)
            visto.append((page.locator(".fw-time-info").inner_text().split("\n")[0], banner(page)))
        paso("área + ▶ 14 ticks", errores=[v for v in visto if v[1]])
        page.screenshot(path=f"{OUT}/06_area_play.png")
        page.get_by_title("Pausar").click()
    else:
        paso("sin canvas de mapa: no se pudo dibujar")

    # Metodología
    page.get_by_title("Metodología").click(); page.wait_for_timeout(1200)
    page.screenshot(path=f"{OUT}/07_metodologia.png")
    paso("metodología", texto=page.inner_text("body")[:0] or "ok", banners=banner(page))

    # Accesibilidad básica
    sin_nombre = page.evaluate("""() => [...document.querySelectorAll('button')].filter(b => !(b.innerText.trim() || b.title || b.getAttribute('aria-label'))).length""")
    paso("botones sin nombre accesible", n=sin_nombre)

    # Móvil
    m = b.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True, locale="es-PE",
                      user_agent="Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36")
    mp = m.new_page(); mp.on("pageerror", lambda e: log["page_errors"].append("MÓVIL " + str(e)[:300]))
    mp.goto(URL, wait_until="domcontentloaded"); mp.wait_for_timeout(7000)
    mp.screenshot(path=f"{OUT}/08_movil.png")
    ov = mp.evaluate("""() => ({sw: document.documentElement.scrollWidth, iw: innerWidth,
        cortados: [...document.querySelectorAll('button, .fw-time-info, .fc-credits')].filter(e => {const r=e.getBoundingClientRect(); return r.width>0 && (r.right>innerWidth+1 || r.left<-1)}).map(e => (e.title||e.innerText||e.className).slice(0,40))})""")
    paso("móvil 375 px", **ov)
    try:
        mp.get_by_title("El fuego en simple: respuestas y gráficos").click(); mp.wait_for_timeout(4000)
        mp.screenshot(path=f"{OUT}/09_movil_en_simple.png", full_page=False); paso("móvil En simple abierto")
    except Exception as e:
        paso("móvil En simple FALLÓ", error=str(e)[:200])
    b.close()

json.dump(log, open(f"{OUT}/ui_log.json", "w"), ensure_ascii=False, indent=1)
print("\nCONSOLE ERRORS:", len(log["console_errors"])); [print("  ", x) for x in sorted(set(log["console_errors"]))[:20]]
print("PAGE ERRORS:", log["page_errors"][:10])
print("API FALLIDAS:", len(log["api_fallidas"])); [print("  ", x) for x in log["api_fallidas"][:40]]
