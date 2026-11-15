"""Descarga diaria de Meteomatics para la comparación EXPLORATORIA con los focos armonizados de Cusco.

Uso (desde la raíz del repo):
    python -I -X utf8 exploratorio/meteomatics/descargar.py <archivo_credenciales.txt>

- Credenciales: se leen de un archivo LOCAL (líneas "Username: ..." y "Password: ..."). Nunca se
  copian al repositorio ni se imprimen.
- Puntos: los 8 centros (ponderados por fuego) de las celdas de 0.5° con más focos armonizados de
  Cusco en 2003-2025 (51 % del fuego); se calculan desde data/harmonized/ y se guardan en puntos.csv.
- Periodo: 2003-2025 (años sin focos extrapolados), un valor diario a las 18 UTC (13:00 local).
- Caché en exploratorio/meteomatics/datos/ (ignorado por git): una consulta por punto y año; si el
  archivo ya existe no se vuelve a pedir. Total: 8 x 23 = 184 consultas (cuota: 1000/día).
"""

from __future__ import annotations

import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "datos"
CELDA_DIA = ROOT / "data" / "harmonized" / "harmonizado_cusco_celda_dia.csv"
ANIOS = range(2003, 2026)
N_PUNTOS = 8
PASO_GRADOS = 0.5
# Nombres verificados en la documentación oficial y con una consulta de prueba (14-nov-2026).
# La cuenta de prueba admite como máximo 10 parámetros por consulta: se dejaron fuera la humedad
# relativa (el VPD ya combina humedad y temperatura) y el viento medio (las rachas lo cubren).
PARAMS = ["fosberg_fire_weather_index:idx", "forest_fire_warning:idx", "drought_index:idx",
          "soil_moisture_deficit:mm", "soil_moisture_index_-15cm:idx",
          "vapor_pressure_deficit_2m:hPa", "evapotranspiration_24h:mm", "wind_gusts_10m_24h:ms",
          "precip_24h:mm", "t_max_2m_24h:C"]
URL = "https://api.meteomatics.com/{t}/{p}/{lat:.4f},{lon:.4f}/csv"


def leer_credenciales(path: Path) -> tuple[str, str]:
    txt = path.read_text(encoding="utf-8")
    user, pwd = (re.search(rf"{k}:\s*(\S+)", txt) for k in ("Username", "Password"))
    if not user or not pwd:
        sys.exit("ERROR: el archivo no tiene lineas 'Username:' y 'Password:'.")
    return user.group(1), pwd.group(1)


def elegir_puntos() -> pd.DataFrame:
    cd = pd.read_csv(CELDA_DIA, dtype={"fecha_local": str})
    cd = cd[cd["calidad"] != "extrapolado"].copy()
    cd["gl"] = np.floor(cd["cell_lat"] / PASO_GRADOS) * PASO_GRADOS
    cd["go"] = np.floor(cd["cell_lon"] / PASO_GRADOS) * PASO_GRADOS
    cd["alt"] = cd["alt_m"].fillna(cd["alt_m"].median())
    filas = []
    for (gl, go), d in cd.groupby(["gl", "go"]):
        w = d["eq_hotspots"]
        filas.append({"celda_lat": gl, "celda_lon": go, "focos": w.sum(),
                      "lat": np.average(d["cell_lat"], weights=w),
                      "lon": np.average(d["cell_lon"], weights=w),
                      "alt_m": np.average(d["alt"], weights=w)})
    g = pd.DataFrame(filas).sort_values("focos", ascending=False).reset_index(drop=True)
    g["parte_del_fuego"] = g["focos"] / g["focos"].sum()
    puntos = g.head(N_PUNTOS).copy()
    puntos.insert(0, "punto", [f"P{i + 1}" for i in range(len(puntos))])
    return puntos.round({"lat": 4, "lon": 4, "alt_m": 0, "focos": 1, "parte_del_fuego": 4})


def descargar(cliente: httpx.Client, punto: pd.Series, anio: int) -> str:
    destino = OUT / f"{punto.punto}_{anio}.csv"
    if destino.exists() and destino.stat().st_size > 1000:
        return f"{destino.name} (en caché)"
    t = f"{anio}-01-01T18:00:00Z--{anio}-12-31T18:00:00Z:P1D"
    for intento in range(3):
        r = cliente.get(URL.format(t=t, p=",".join(PARAMS), lat=punto.lat, lon=punto.lon))
        if r.status_code == 200:
            destino.write_text(r.text, encoding="utf-8")
            return f"{destino.name} ({len(r.text.splitlines()) - 1} días)"
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(10 * (intento + 1))
            continue
        raise RuntimeError(f"{destino.name}: HTTP {r.status_code} {r.text[:200]}")
    raise RuntimeError(f"{destino.name}: sin respuesta tras 3 intentos")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    auth = leer_credenciales(Path(sys.argv[1]))
    OUT.mkdir(parents=True, exist_ok=True)
    puntos = elegir_puntos()
    puntos.to_csv(OUT.parent / "puntos.csv", index=False)
    print(f"{len(puntos)} puntos (cubren {puntos['parte_del_fuego'].sum():.0%} del fuego)")
    tareas = [(p, a) for _, p in puntos.iterrows() for a in ANIOS]
    with httpx.Client(auth=auth, timeout=180) as cliente, ThreadPoolExecutor(4) as pool:
        futuros = {pool.submit(descargar, cliente, p, a): (p.punto, a) for p, a in tareas}
        for i, f in enumerate(as_completed(futuros), start=1):
            try:
                print(f"[{i}/{len(tareas)}] {f.result()}", flush=True)
            except Exception as exc:  # noqa: BLE001 - se informa y se sigue con las demás
                print(f"[{i}/{len(tareas)}] ERROR {exc}", flush=True)


if __name__ == "__main__":
    main()
