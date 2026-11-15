"""Auditoria estatica: paleta (contraste WCAG, daltonismo), tipografia y modulos alcanzables.

Uso: python auditoria_estatica.py <carpeta plataforma_local>
"""
from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
SRC = ROOT / "frontend" / "src"
css = (SRC / "fire-map.css").read_text(encoding="utf-8") + (SRC / "firecal.css").read_text(encoding="utf-8")
jsx = (SRC / "FireMapApp.jsx").read_text(encoding="utf-8")
charts = (SRC / "charts.js").read_text(encoding="utf-8")


def rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def lin(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(c):
    r, g, b = (lin(x) for x in c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def over(fg, alpha, bg):
    return tuple(round(alpha * f + (1 - alpha) * b) for f, b in zip(fg, bg))


# Machado et al. 2009, severidad 1.0
CVD = {"deuteranopia": [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.011820, 0.042940, 0.968881]],
       "protanopia": [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]]}


def sim(c, kind):
    l = [lin(x) for x in c]
    out = [sum(m * v for m, v in zip(row, l)) for row in CVD[kind]]
    return tuple(max(0.0, min(1.0, v)) for v in out)


def dist(a, b, kind=None):
    """Distancia aproximada (0-1, RGB lineal) entre dos colores, opcionalmente simulando daltonismo."""
    pa = sim(a, kind) if kind else tuple(lin(x) for x in a)
    pb = sim(b, kind) if kind else tuple(lin(x) for x in b)
    return sum((x - y) ** 2 for x, y in zip(pa, pb)) ** 0.5


print("=" * 70, "\n1. INVENTARIO DE COLOR")
for name, text in (("CSS (fire-map + firecal)", css), ("FireMapApp.jsx", jsx), ("charts.js", charts)):
    hexes = Counter(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", text))
    rgbas = Counter(re.sub(r"\s", "", r) for r in re.findall(r"rgba?\([^)]*\)", text))
    print(f"  {name}: {len(hexes)} hex distintos, {len(rgbas)} rgba distintos")
todos = Counter(h.lower() for h in re.findall(r"#[0-9a-fA-F]{6}\b", css + jsx + charts))
print(f"  TOTAL hex distintos (6 digitos): {len(todos)}")
print("  mas usados:", ", ".join(f"{h}x{n}" for h, n in todos.most_common(14)))
print("  variables CSS:", re.findall(r"--[a-z]+", re.search(r":root\{[^}]*\}", css).group(0)))

print("=" * 70, "\n2. CONTRASTE (WCAG: texto normal >= 4.5, grande >= 3)")
PANEL = over((8, 22, 18), 0.92, (40, 60, 52))  # panel sobre mapa medio
pairs = [
    ("texto base #f7fbf8 / panel", "#f7fbf8", PANEL),
    ("--muted #98a8a1 / panel", "#98a8a1", PANEL),
    ("--green #b8f36b / panel (rotulos 8px)", "#b8f36b", PANEL),
    ("th calendario #8fa098 / panel (8px)", "#8fa098", PANEL),
    ("leyenda #9fb0a8 / panel (9px)", "#9fb0a8", PANEL),
    ("creditos #83938b / panel (8px)", "#83938b", PANEL),
    ("margen #ffbc5d / panel", "#ffbc5d", PANEL),
    ("error #f87171 / panel", "#f87171", PANEL),
]
for label, fg, bg in pairs:
    c = contrast(rgb(fg), bg)
    print(f"  {c:5.2f}  {'OK ' if c >= 4.5 else 'BAJO'}  {label}")
print("  -- celdas del calendario (numero sobre color) --")
YL = ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"]


def ink(color):
    r, g, b = rgb(color)
    return "#1d2330" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#f7fbf8"


for col in ["#2a3a34", *YL]:
    i = ink(col)
    c = contrast(rgb(i), rgb(col))
    alt = contrast(rgb("#1d2330" if i == "#f7fbf8" else "#f7fbf8"), rgb(col))
    print(f"  {c:5.2f}  {'OK ' if c >= 4.5 else 'BAJO'}  tinta {i} sobre {col}  (la otra tinta daria {alt:.2f})")
for col in YL:  # extrapolado: opacity .55 sobre panel
    bg = over(rgb(col), 0.55, PANEL)
    i = over(rgb(ink(col)), 0.55, PANEL)
    print(f"  {contrast(i, bg):5.2f}  {'OK ' if contrast(i, bg) >= 4.5 else 'BAJO'}  extrapolado (opacidad .55) sobre {col}")
print("  -- modo anomalia: texto claro #f7fbf8 sobre rojo/azul con alfa --")
for a in (0.5, 1.0, 2.0):
    alpha = min(1, 0.25 + a / 2.5)
    red = over((240, 59, 32), alpha, PANEL)
    blue = over((103, 169, 207), alpha, PANEL)
    print(f"  anomalia +{a}: {contrast(rgb('#f7fbf8'), red):5.2f} (rojo)   anomalia -{a}: {contrast(rgb('#f7fbf8'), blue):5.2f} (azul)")

print("=" * 70, "\n3. DALTONISMO (distancia entre colores; < 0.10 = dificil de distinguir)")
tests = [("puntos MODIS #ff9b3f vs VIIRS #f33932", "#ff9b3f", "#f33932"),
         ("YlOrRd clase 3 vs 4", YL[2], YL[3]), ("YlOrRd clase 4 vs 5", YL[3], YL[4]),
         ("YlOrRd clase 1 vs 2", YL[0], YL[1]),
         ("anomalia rojo vs azul", "#f03b20", "#67a9cf"),
         ("graficos naranja #c2410c vs azul #31688e", "#c2410c", "#31688e"),
         ("graficos azul #31688e vs azul claro #9ecae1", "#31688e", "#9ecae1")]
risk = dict(re.findall(r"\.fw-risk--(\w+)\{color:(#[0-9a-fA-F]{6})", css))
print("  insignias de categoria (fw-risk):", risk)
keys = list(risk)
for i in range(len(keys)):
    for j in range(i + 1, len(keys)):
        tests.append((f"insignia {keys[i]} vs {keys[j]}", risk[keys[i]], risk[keys[j]]))
for label, a, b in tests:
    d0, d1, d2 = dist(rgb(a), rgb(b)), dist(rgb(a), rgb(b), "deuteranopia"), dist(rgb(a), rgb(b), "protanopia")
    flag = "DIFICIL" if min(d1, d2) < 0.10 else "ok"
    print(f"  normal {d0:.2f} | deuter. {d1:.2f} | protan. {d2:.2f}  {flag:8} {label}")

print("=" * 70, "\n4. TIPOGRAFIA")
sizes = Counter()
for m in re.finditer(r"font(?:-size)?:\s*(?:\d+\s+)?(\d+(?:\.\d+)?)px", css):
    sizes[float(m.group(1))] += 1
tot = sum(sizes.values())
small = sum(n for s, n in sizes.items() if s < 11)
print("  tamanos (px: veces):", dict(sorted(sizes.items())))
print(f"  declaraciones < 11 px: {small} de {tot} ({100 * small / tot:.0f} %); minimo {min(sizes)} px")
print("  media queries:", sorted(set(re.findall(r"@media\(([^)]*)\)", css))))
print("  :focus / focus-visible en CSS:", len(re.findall(r":focus", css)), "| prefers-reduced-motion:", "prefers-reduced-motion" in css,
      "| prefers-color-scheme:", "prefers-color-scheme" in css)
print("  aria-label en JSX:", jsx.count("aria-label"), "| title=:", jsx.count("title="), "| <td onClick sin teclado:", "td key={m} title={tip} onClick" in jsx)

print("=" * 70, "\n5. MODULOS DEL BACKEND: que usa la app publicada (legacy_v1: false)")
BK = ROOT / "backend"
mods = {}
for f in list((BK / "firecal").rglob("*.py")) + list((BK / "api").rglob("*.py")):
    name = ".".join(f.relative_to(BK).with_suffix("").parts)
    name = name[:-9] if name.endswith(".__init__") else name
    mods[name] = f


def imports(path):
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return {m for m in out if m in mods}


def reach(starts):
    seen, todo = set(), list(starts)
    while todo:
        m = todo.pop()
        if m in seen or m not in mods:
            continue
        seen.add(m)
        todo += imports(mods[m])
    return seen


lines = {m: sum(1 for _ in f.open(encoding="utf-8")) for m, f in mods.items()}
vivo = reach(["api.routers.plan", "api.limits", "firecal.plan.events", "firecal.plan.analitica"]) | {"api.main"}
total = sum(lines.values())
lv = sum(lines[m] for m in vivo)
print(f"  modulos: {len(mods)} | lineas: {total}")
print(f"  usados por /api/* + plan-events: {len(vivo)} modulos, {lv} lineas ({100 * lv / total:.0f} %)")
print("   ", ", ".join(sorted(vivo)))
muerto = sorted(set(mods) - vivo, key=lambda m: -lines[m])
print(f"  solo para el backend sintetico apagado (/api/v1) o su pipeline: {len(muerto)} modulos, {total - lv} lineas ({100 * (total - lv) / total:.0f} %)")
grupos = Counter()
for m in muerto:
    grupos[".".join(m.split(".")[:2])] += lines[m]
print("   ", ", ".join(f"{g} {n}" for g, n in grupos.most_common()))
tests = Counter()
for f in (BK / "tests").glob("test_*.py"):
    tests[f.name] = len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), flags=re.M))
print("  pruebas por archivo:", dict(tests))
