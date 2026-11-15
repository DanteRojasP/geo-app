"""Verifica qué herramientas hay para la evaluación preventiva (PROTOCOLO_PREVENTIVO.md §5).

Comprueba paquetes de Python, archivos de credenciales, el estado de las claves de FIRMS y
Meteomatics, las APIs activas de Google Cloud y el acceso a las fuentes públicas. No imprime
ninguna clave, usuario ni correo: las claves se leen solo en memoria.

Uso (desde la raíz del repo):
    python -I -X utf8 exploratorio/preventivo/verificar_herramientas.py [carpeta_de_credenciales]

La carpeta de credenciales (fuera del repo) puede tener credenciales_firms.txt y
credenciales_meteo.txt. Sin ella, se omiten esas dos comprobaciones.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import httpx

CRED = Path(sys.argv[1]) if len(sys.argv) > 1 else None
GCP_PROJECT = os.environ.get("FIRECAL_GCP_PROJECT", "sonic-mile-514718-r5")
HOME = Path.home()
c = httpx.Client(timeout=45, follow_redirects=True, headers={"User-Agent": "firecal-check/1.0"})


def titulo(t: str) -> None:
    print(f"\n== {t} ==")


def get(nombre: str, url: str, params: dict | None = None, leer=None, **kw) -> None:
    try:
        r = c.get(url, params=params, **kw)
        extra = ""
        if leer and r.status_code == 200:
            try:
                extra = " | " + str(leer(r))
            except Exception as exc:          # noqa: BLE001 - es un diagnóstico: cualquier fallo se informa
                extra = f" | (respuesta no esperada: {type(exc).__name__})"
        print(f"  [{r.status_code}] {nombre}{extra}")
    except httpx.HTTPError as exc:
        print(f"  [sin respuesta] {nombre} | {type(exc).__name__}")


# ---------------------------------------------------------------- 1. paquetes de Python
titulo("Paquetes de Python en este entorno")
PAQUETES = {"pandas": "tablas", "numpy": "cálculo", "scipy": "estadística", "sklearn": "modelos",
            "shapely": "geometría", "duckdb": "consultas", "httpx": "descargas",
            "ee": "Earth Engine (earthengine-api)", "xarray": "grillas (ERA5, CHIRPS)",
            "netCDF4": "leer NetCDF", "rasterio": "leer GeoTIFF", "geopandas": "límites y zonas",
            "statsmodels": "modelos con errores agrupados", "cdsapi": "Copernicus (FWI, ERA5-Land)",
            "pystac_client": "catálogo de Planetary Computer", "planetary_computer": "firmar descargas",
            "xclim": "calcular el índice FWI", "zarr": "ERA5 en la nube"}
for mod, uso in PAQUETES.items():
    print(f"  {'instalado' if importlib.util.find_spec(mod) else 'FALTA    '}  {mod:20} {uso}")

# ---------------------------------------------------------------- 2. credenciales guardadas
titulo("Credenciales guardadas (solo se comprueba si el archivo existe)")
ARCHIVOS = {"Earth Engine": [HOME / ".config/earthengine/credentials"],
            "Google Cloud (ADC)": [Path(os.environ.get("APPDATA", HOME)) / "gcloud/application_default_credentials.json",
                                   HOME / ".config/gcloud/application_default_credentials.json"],
            "Copernicus CDS/EWDS": [HOME / ".cdsapirc"],
            "NASA Earthdata": [HOME / ".netrc", HOME / "_netrc"]}
for nombre, rutas in ARCHIVOS.items():
    print(f"  {'hay  ' if any(p.is_file() for p in rutas) else 'FALTA'}  {nombre}")
for f in ("credenciales_firms.txt", "credenciales_meteo.txt"):
    print(f"  {'hay  ' if CRED and (CRED / f).is_file() else 'no se indicó o falta'}  {f}")

# ---------------------------------------------------------------- 3. NASA FIRMS
titulo("NASA FIRMS (MAP_KEY)")
if CRED and (CRED / "credenciales_firms.txt").is_file():
    m = re.search(r"\b[0-9a-fA-F]{32}\b", (CRED / "credenciales_firms.txt").read_text(encoding="utf-8-sig"))
    if m:
        k = m.group(0)
        get("cuota de la clave", "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/", {"MAP_KEY": k},
            lambda r: f"{r.json()['current_transactions']} de {r.json()['transaction_limit']} en "
                      f"{r.json()['transaction_interval']}")
        get("disponibilidad por fuente", f"https://firms.modaps.eosdis.nasa.gov/api/data_availability/csv/{k}/all",
            None, lambda r: "\n      " + "\n      ".join(r.text.strip().splitlines()[1:]))
        k = None
else:
    print("  (omitido)")

# ---------------------------------------------------------------- 4. Meteomatics
titulo("Meteomatics")
if CRED and (CRED / "credenciales_meteo.txt").is_file():
    txt = (CRED / "credenciales_meteo.txt").read_text(encoding="utf-8")
    u, p = (re.search(rf"{x}:\s*(\S+)", txt) for x in ("Username", "Password"))
    if u and p:
        def stats(r):
            s = r.json().get("user statistics", r.json())
            return (f"vence {s.get('hard deadline')} | hoy {s['requests since last UTC midnight']['used']} de "
                    f"{s['requests since last UTC midnight']['hard limit']} solicitudes | histórico "
                    f"{s.get('historic request option')}")
        get("estado de la cuenta", "https://api.meteomatics.com/user_stats_json", None, stats,
            auth=(u.group(1), p.group(1)))
else:
    print("  (omitido)")

# ---------------------------------------------------------------- 5. Google Cloud
titulo(f"Google Cloud (proyecto {GCP_PROJECT})")
gcloud = shutil.which("gcloud.cmd") or shutil.which("gcloud")
if gcloud:
    out = subprocess.run([gcloud, "services", "list", "--enabled", "--project", GCP_PROJECT,
                          "--format", "value(config.name)"], capture_output=True, text=True, check=False).stdout
    activas = set(out.split())
    for api, uso in {"run.googleapis.com": "servidor y tareas", "storage.googleapis.com": "guardar tablas",
                     "secretmanager.googleapis.com": "claves", "bigquery.googleapis.com": "consultas",
                     "earthengine.googleapis.com": "Earth Engine",
                     "cloudscheduler.googleapis.com": "tarea diaria programada"}.items():
        print(f"  {'activa' if api in activas else 'FALTA '}  {api:32} {uso}")
    fact = subprocess.run([gcloud, "billing", "projects", "describe", GCP_PROJECT, "--format",
                           "value(billingEnabled)"], capture_output=True, text=True, check=False).stdout.strip()
    print(f"  facturación activa: {fact or 'no se pudo leer'} (el crédito restante solo se ve en la consola)")
else:
    print("  gcloud no está en el PATH")

# ---------------------------------------------------------------- 6. fuentes públicas
titulo("Fuentes sin clave")
P = {"latitude": -13.52, "longitude": -71.97}
get("Open-Meteo histórico (ERA5), 1981", "https://archive-api.open-meteo.com/v1/archive",
    {**P, "start_date": "1981-08-01", "end_date": "1981-08-02", "daily": "precipitation_sum"},
    lambda r: r.json()["daily"]["time"])
get("Open-Meteo pronóstico de 16 días", "https://api.open-meteo.com/v1/forecast",
    {**P, "daily": "precipitation_sum", "forecast_days": 16}, lambda r: "hasta " + r.json()["daily"]["time"][-1])
get("Open-Meteo estacional", "https://seasonal-api.open-meteo.com/v1/seasonal",
    {**P, "daily": "precipitation_sum", "forecast_days": 183}, lambda r: "hasta " + r.json()["daily"]["time"][-1])
get("NASA POWER (MERRA-2)", "https://power.larc.nasa.gov/api/temporal/daily/point",
    {"parameters": "T2M_MAX,PRECTOTCORR", "community": "AG", "longitude": -71.97, "latitude": -13.52,
     "start": "20050801", "end": "20050802", "format": "JSON"}, lambda r: "ok")
get("NOAA ONI (El Niño)", "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt", None,
    lambda r: "último: " + " ".join(r.text.strip().splitlines()[-1].split()))
get("CHIRPS (UCSB)", "https://data.chc.ucsb.edu/products/CHIRPS/", None,
    lambda r: ", ".join(re.findall(r'href="(v[0-9.]+/)"', r.text)))
get("PISCO de SENAMHI (IRI)", "https://iridl.ldeo.columbia.edu/SOURCES/.SENAMHI/.HSR/.PISCO/", None, lambda r: "ok")
get("GWIS (mapas de FWI, solo visual)", "https://maps.effis.emergency.copernicus.eu/gwis",
    {"service": "WMS", "request": "GetCapabilities"}, lambda r: f"{r.text.count('<Layer')} capas")
get("ERA5 público en Google Cloud", "https://storage.googleapis.com/storage/v1/b/gcp-public-data-arco-era5/o",
    {"prefix": "ar/", "delimiter": "/", "maxResults": 3}, lambda r: f"{len(r.json().get('prefixes', []))}+ carpetas")
for cid in ("modis-64A1-061", "modis-13A1-061", "modis-14A1-061", "io-lulc-annual-v02", "cop-dem-glo-30", "era5-pds"):
    get(f"Planetary Computer: {cid}", f"https://planetarycomputer.microsoft.com/api/stac/v1/collections/{cid}",
        None, lambda r: r.json().get("title"))

titulo("Fuentes que piden cuenta (se comprueba solo que el servicio responde)")
get("Copernicus EWDS: FWI histórico", "https://ewds.climate.copernicus.eu/api/catalogue/v1/collections/cems-fire-historical-v1",
    None, lambda r: r.json().get("title", "")[:70])
get("Copernicus EWDS: FWI estacional", "https://ewds.climate.copernicus.eu/api/catalogue/v1/collections/cems-fire-seasonal",
    None, lambda r: r.json().get("title", "")[:70])
get("Copernicus CDS: ERA5-Land", "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-land",
    None, lambda r: r.json().get("title", "")[:70])
get("NASA AppEEARS", "https://appeears.earthdatacloud.nasa.gov/api/product", None,
    lambda r: f"{len(r.json())} productos")
