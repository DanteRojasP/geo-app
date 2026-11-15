"""Descarga Meteomatics en el centro de las 99 zonas de ~28 km de Cusco (2003-2025, diario a las 18 UTC).

Mismas zonas que el protocolo preventivo (exploratorio/preventivo/linea_base.py): celdas de 0,25° cuyo
centro cae dentro de Cusco. A diferencia de descargar.py (8 puntos elegidos por su fuego), aquí las zonas
cubren todo el departamento y no dependen del fuego.

Uso (desde la raíz del repo):
    python -I -X utf8 exploratorio/meteomatics/descargar_zonas.py <credenciales_meteo.txt>

Una solicitud por año (99 puntos x 365 días x 10 parámetros, ~3 MB, ~20 s). Los datos de Meteomatics no se
publican: quedan en exploratorio/meteomatics/datos/zonas/ (ignorado por git).
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
from shapely import contains_xy

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "preventivo"))
import linea_base

OUT = AQUI / "datos" / "zonas"
PASO = 0.25
ANIOS = range(2003, 2026)
PARAMS = ["fosberg_fire_weather_index:idx", "forest_fire_warning:idx", "drought_index:idx",
          "soil_moisture_deficit:mm", "soil_moisture_index_-15cm:idx", "vapor_pressure_deficit_2m:hPa",
          "evapotranspiration_24h:mm", "wind_gusts_10m_24h:ms", "precip_24h:mm", "t_max_2m_24h:C"]


def zonas() -> pd.DataFrame:
    geom = linea_base.limite()
    w, s, e, n = geom.bounds
    ii = np.arange(int(np.floor(s / PASO)), int(np.floor(n / PASO)) + 1)
    jj = np.arange(int(np.floor(w / PASO)), int(np.floor(e / PASO)) + 1)
    gi, gj = np.meshgrid(ii, jj, indexing="ij")
    lat, lon = (gi + 0.5) * PASO, (gj + 0.5) * PASO
    m = contains_xy(geom, lon, lat)
    return pd.DataFrame({"zi": gi[m], "zj": gj[m], "lat": lat[m], "lon": lon[m]})


def leer_credenciales(path: Path) -> tuple[str, str]:
    txt = path.read_text(encoding="utf-8")
    u, p = (re.search(rf"{k}:\s*(\S+)", txt) for k in ("Username", "Password"))
    if not u or not p:
        sys.exit("ERROR: el archivo no tiene líneas 'Username:' y 'Password:'.")
    return u.group(1), p.group(1)


def bajar(cliente: httpx.Client, pts: str, anio: int) -> str:
    destino = OUT / f"z_{anio}.csv"
    if destino.exists() and destino.stat().st_size > 100_000:
        return f"{destino.name} (en caché)"
    url = (f"https://api.meteomatics.com/{anio}-01-01T18:00:00Z--{anio}-12-31T18:00:00Z:P1D/"
           f"{','.join(PARAMS)}/{pts}/csv")
    for intento in range(3):
        r = cliente.get(url)
        if r.status_code == 200:
            destino.write_text(r.text, encoding="utf-8")
            return f"{destino.name} ({len(r.text.splitlines()) - 1:,} filas)"
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(15 * (intento + 1))
            continue
        raise RuntimeError(f"{destino.name}: HTTP {r.status_code}")    # sin el texto: puede traer el usuario
    raise RuntimeError(f"{destino.name}: sin respuesta tras 3 intentos")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    auth = leer_credenciales(Path(sys.argv[1]))
    OUT.mkdir(parents=True, exist_ok=True)
    z = zonas()
    z.to_csv(OUT / "zonas.csv", index=False)
    pts = "+".join(f"{a:.3f},{b:.3f}" for a, b in zip(z.lat, z.lon, strict=True))
    print(f"{len(z)} zonas; {len(ANIOS)} solicitudes")
    with httpx.Client(auth=auth, timeout=600) as cliente, ThreadPoolExecutor(3) as pool:
        fut = {pool.submit(bajar, cliente, pts, a): a for a in ANIOS}
        for i, f in enumerate(as_completed(fut), start=1):
            try:
                print(f"[{i}/{len(ANIOS)}] {f.result()}", flush=True)
            except Exception as exc:  # noqa: BLE001 - se informa y se sigue
                print(f"[{i}/{len(ANIOS)}] ERROR {exc}", flush=True)


if __name__ == "__main__":
    main()
