"""Simulador de focos de calor con el formato de los CSV de FIRMS.

Modelo generativo (todo vectorizado con numpy, semilla fija; parámetros en
``config/settings.yaml`` -> ``synthetic``):

1. Paisaje: peso espacial por celda H3 dentro del bbox = fondo + mezcla de gaussianas
   ("zonas calientes").
2. Eventos: N mensual ~ Poisson(base x estacionalidad x factor_anual x scale).
3. Cada evento: celda elegida por peso, tamaño lognormal, duración geométrica (más larga
   si es grande); cada día tiene un área activa.
4. Detección por pasada (satélite x día/noche): señal = área activa x ciclo diurno;
   p = logística(log(señal / s50) / slope) x cobertura x (1 - nubosidad).
   Detecciones por pasada = 1 + Poisson(área / píxel - 1).
5. Periodos activos por satélite y deriva orbital de Terra/Aqua como cambio de la hora
   de paso (``overpass_drift``): el efecto sobre la detección sale del ciclo diurno.
6. Ruido: fuentes industriales fijas (type = 2), duplicados bow-tie en MODIS, últimos
   ``nrt_days`` como SYN-NRT sin columna ``type``.
7. Verdad: ``truth.parquet`` (conteos mensuales esperados y realizados por satélite, mes
   local y día/noche) y ``truth_events.parquet`` (un evento por fila).
8. ``manifest.json`` con los parámetros usados.

Los datos son SINTÉTICOS: no representan focos reales.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import h3
import numpy as np
import pandas as pd

from firecal import __version__
from firecal.settings import Settings, SyntheticParams

log = logging.getLogger(__name__)

GENERATOR_VERSION = "synth-v0.1"
KM_PER_DEG_LAT = 111.32
EPOCH = date(1970, 1, 1)
SATELLITES = ("TERRA", "AQUA", "SNPP", "N20", "N21")
PASSES = ("D", "N")

MODIS_COLUMNS = [
    "latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type",
]
VIIRS_COLUMNS = [
    "latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version", "bright_ti5", "frp", "daynight", "type",
]

# Coeficientes SOLO cosméticos para que las columnas radiométricas tengan valores plausibles.
# El pipeline no los usa (solo usa posición, fecha/hora, satélite, confianza, día/noche y type).
# k = "intensidad" de la detección en [0, 1].
_COSMETIC = {
    "MODIS": {
        "bt_main": (305.0, 60.0, 6.0),    # brightness = a + b*k + N(0, c)  [K]
        "bt_main_night_drop": 10.0,
        "bt_aux": (290.0, 10.0, 4.0),     # bright_t31
        "frp_log": (np.log(8.0), 1.5, 0.8),
        "scan": (1.0, 3.8), "track": (1.0, 1.0),
        "conf": (30.0, 70.0, 12.0),       # confianza 0-100
        "lat_decimals": 4, "frp_decimals": 1, "scan_decimals": 1,
    },
    "VIIRS": {
        "bt_main": (300.0, 55.0, 8.0),    # bright_ti4
        "bt_main_night_drop": 10.0,
        "bt_main_saturation": 367.0,      # el canal I4 satura cerca de 367 K
        "bt_aux": (285.0, 15.0, 4.0),     # bright_ti5
        "frp_log": (np.log(1.5), 1.5, 0.8),
        "scan": (0.32, 0.48), "track": (0.36, 0.42),
        "conf_noise": 0.15, "conf_low": 0.3, "conf_high": 0.95,
        "lat_decimals": 5, "frp_decimals": 2, "scan_decimals": 2,
    },
    "industrial_k": (0.6, 1.0),           # las fuentes fijas son calientes
}


def _build_lattice(radius: int) -> np.ndarray:
    """Puntos enteros (x, y) ordenados por distancia al origen: posiciones de píxel vecinos.

    La detección j de una pasada ocupa el píxel j de esta lista, así las detecciones de un
    mismo fuego quedan en píxeles distintos (separados >= 1 píxel), como en los datos reales.
    """
    r = np.arange(-radius, radius + 1)
    xx, yy = np.meshgrid(r, r)
    pts = np.column_stack([xx.ravel(), yy.ravel()])
    order = np.lexsort((np.arctan2(pts[:, 1], pts[:, 0]), np.hypot(pts[:, 0], pts[:, 1])))
    return pts[order].astype(float)


_LATTICE = _build_lattice(60)  # 14 641 píxeles: tope de detecciones por fuego y pasada


@dataclass
class SynthResult:
    """Resumen de una corrida del simulador."""

    out_dir: Path
    rows_per_file: dict[str, int]
    elapsed_s: float
    n_events: int
    manifest: dict = field(repr=False)

    @property
    def total_rows(self) -> int:
        return sum(self.rows_per_file.values())


# --------------------------------------------------------------------------------------
# Utilidades de fechas (días desde 1970-01-01 como enteros, para vectorizar)
# --------------------------------------------------------------------------------------
def _to_day(d: date) -> int:
    return (d - EPOCH).days


def _days_to_dt64(days: np.ndarray) -> np.ndarray:
    return days.astype("datetime64[D]")


def _month_index(days: np.ndarray) -> np.ndarray:
    """Meses desde 1970-01 (0 = ene-1970)."""
    return _days_to_dt64(days).astype("datetime64[M]").astype(np.int64)


def _utc_offset_hours(tz_name: str, start: date, end: date) -> float:
    """Desfase UTC de la zona horaria; exige que sea constante en el periodo (Lima: -5 h)."""
    tz = ZoneInfo(tz_name)
    offsets = {
        tz.utcoffset(datetime(y, m, 15)).total_seconds() / 3600
        for y in range(start.year, end.year + 1)
        for m in (1, 7)
    }
    if len(offsets) != 1:
        raise ValueError(
            f"La zona {tz_name} tiene horario de verano en el periodo; el simulador asume "
            f"desfase constante. Desfases encontrados: {sorted(offsets)}"
        )
    return offsets.pop()


def resolve_end(params: SyntheticParams, tz_name: str) -> date:
    """Fecha final: la configurada o 'hoy' en la zona horaria del proyecto."""
    return params.end or datetime.now(ZoneInfo(tz_name)).date()


# --------------------------------------------------------------------------------------
# 1. Paisaje
# --------------------------------------------------------------------------------------
def build_landscape(settings: Settings, rng: np.random.Generator) -> dict:
    """Celdas H3 del bbox con su peso espacial (suma 1) y las zonas calientes usadas."""
    p = settings.params
    w, s, e, n = p.region.bbox
    res = p.grid.h3_res_store
    poly = h3.LatLngPoly([(s, w), (s, e), (n, e), (n, w)])
    cells = np.array(sorted(h3.polygon_to_cells(poly, res)))
    centers = np.array([h3.cell_to_latlng(c) for c in cells])  # (lat, lon)
    lat, lon = centers[:, 0], centers[:, 1]

    land = p.synthetic.landscape
    n_zones = int(rng.integers(land.n_hot_zones[0], land.n_hot_zones[1] + 1))
    z_lat = rng.uniform(s, n, n_zones)
    z_lon = rng.uniform(w, e, n_zones)
    z_sigma = rng.uniform(*land.zone_sigma_deg, n_zones)
    z_amp = rng.uniform(*land.zone_amplitude, n_zones)

    coslat = np.cos(np.deg2rad((s + n) / 2))
    weight = np.full(cells.size, land.background_weight)
    for zl, zo, zs, za in zip(z_lat, z_lon, z_sigma, z_amp, strict=True):
        d2 = (lat - zl) ** 2 + ((lon - zo) * coslat) ** 2
        weight += za * np.exp(-d2 / (2 * zs**2))
    weight /= weight.sum()

    zones = [
        {"lat": float(a), "lon": float(b), "sigma_deg": float(c), "amplitude": float(d)}
        for a, b, c, d in zip(z_lat, z_lon, z_sigma, z_amp, strict=True)
    ]
    return {"cells": cells, "lat": lat, "lon": lon, "weight": weight, "zones": zones}


# --------------------------------------------------------------------------------------
# 2. Factores temporales
# --------------------------------------------------------------------------------------
def annual_factors(
    params: SyntheticParams, start: date, end: date, rng: np.random.Generator
) -> tuple[dict[int, float], list[int]]:
    """Factor anual lognormal x tendencia, con 2-3 años extremos (elegidos entre años completos)."""
    ev = params.events
    years = list(range(start.year, end.year + 1))
    noise = np.exp(rng.normal(0.0, ev.annual_sigma, len(years)))
    trend = 1.0 + ev.trend_per_year * (np.array(years) - years[0])
    factors = dict(zip(years, noise * trend, strict=True))

    full_years = [y for y in years if date(y, 1, 1) >= start and date(y, 12, 31) <= end]
    n_ext = int(rng.integers(ev.n_extreme_years[0], ev.n_extreme_years[1] + 1))
    n_ext = min(n_ext, len(full_years))
    extremes = sorted(int(y) for y in rng.choice(full_years, n_ext, replace=False))
    for y in extremes:
        factors[y] *= rng.uniform(*ev.extreme_multiplier)
    return {int(k): float(v) for k, v in factors.items()}, extremes


def diurnal_factor(hour_local: np.ndarray, params: SyntheticParams) -> np.ndarray:
    """Intensidad relativa según la hora local: máximo en ``peak_hour``, mínimo de madrugada."""
    d = params.diurnal
    phase = (1 + np.cos(2 * np.pi * (hour_local - d.peak_hour) / 24)) / 2
    return d.min_factor + (1 - d.min_factor) * phase**d.sharpness


def overpass_shift(sat: str, days: np.ndarray, params: SyntheticParams) -> np.ndarray:
    """Desplazamiento (horas) de la hora de paso por deriva orbital; 0 si no hay deriva."""
    nodes = params.overpass_drift.get(sat)
    if not nodes:
        return np.zeros(days.shape)
    x = np.array([_to_day(d) for d, _ in nodes], dtype=float)
    y = np.array([h for _, h in nodes]) - nodes[0][1]
    return np.interp(days, x, y)  # constante antes del primer y después del último nodo


# --------------------------------------------------------------------------------------
# 3. Eventos de un año
# --------------------------------------------------------------------------------------
def simulate_events(
    year: int,
    start: date,
    end: date,
    factor: float,
    scale: float,
    land: dict,
    params: SyntheticParams,
    rng: np.random.Generator,
    first_id: int,
) -> pd.DataFrame:
    """Eventos que empiezan en ``year`` (dentro de [start, end])."""
    ev = params.events
    season = np.asarray(ev.seasonality) / np.mean(ev.seasonality)
    starts, counts = [], []
    for m in range(1, 13):
        m0 = max(date(year, m, 1), start)
        m1 = min((date(year, m, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), end)
        if m1 < m0:
            continue
        n_days_in_month = ((date(year, m, 28) + timedelta(days=4)).replace(day=1)
                           - date(year, m, 1)).days
        n_days = (m1 - m0).days + 1
        lam = ev.base_per_month * season[m - 1] * factor * scale * n_days / n_days_in_month
        k = int(rng.poisson(lam))
        starts.append(_to_day(m0) + rng.integers(0, n_days, k))
        counts.append(k)
    start_day = np.concatenate(starts) if starts else np.array([], dtype=np.int64)
    n = start_day.size

    cell_idx = rng.choice(land["cells"].size, size=n, p=land["weight"])
    lat0 = land["lat"][cell_idx]
    jit = params.events.location_jitter_km
    lat = lat0 + rng.normal(0, jit, n) / KM_PER_DEG_LAT
    lon = land["lon"][cell_idx] + rng.normal(0, jit, n) / (
        KM_PER_DEG_LAT * np.cos(np.deg2rad(lat0))
    )
    size = np.minimum(ev.size_ha_median * np.exp(rng.normal(0, ev.size_ha_sigma, n)),
                      ev.size_ha_max)
    mean_dur = 1 + ev.duration_coef * np.log1p(size / ev.duration_ref_ha)
    duration = rng.geometric(1 / mean_dur)
    return pd.DataFrame({
        "event_id": np.arange(first_id, first_id + n, dtype=np.int64),
        "start_day": start_day.astype(np.int64),
        "lat": lat, "lon": lon,
        "h3": land["cells"][cell_idx],
        "size_ha": size,
        "duration_days": duration.astype(np.int64),
    })


def expand_event_days(events: pd.DataFrame, end_day: int, params: SyntheticParams,
                      rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Una fila por evento x día activo, con el área activa de ese día."""
    dur = events["duration_days"].to_numpy()
    idx = np.repeat(np.arange(len(events)), dur)
    offsets = np.arange(idx.size) - np.repeat(np.cumsum(dur) - dur, dur)
    day = events["start_day"].to_numpy()[idx] + offsets
    keep = day <= end_day
    idx, day = idx[keep], day[keep]
    size = events["size_ha"].to_numpy()[idx]
    area = size / dur[idx] * np.exp(rng.normal(0, params.events.daily_area_sigma, idx.size))
    return {
        "event": idx, "day": day, "area_ha": area, "size_ha": size,
        "lat": events["lat"].to_numpy()[idx], "lon": events["lon"].to_numpy()[idx],
    }


# --------------------------------------------------------------------------------------
# 4. Detección
# --------------------------------------------------------------------------------------
def _sat_active(sat_cfg, days: np.ndarray, end_day: int) -> np.ndarray:
    last = _to_day(sat_cfg.end) if sat_cfg.end else end_day
    return (days >= _to_day(sat_cfg.start)) & (days <= last)


def _pixel_size_km(sensor: str, u2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Tamaño de píxel (scan, track) en km según la posición en el barrido (u2 en [0, 1])."""
    c = _COSMETIC[sensor]
    return c["scan"][0] + c["scan"][1] * u2, c["track"][0] + c["track"][1] * u2


def _attributes(sensor: str, k: np.ndarray, night: np.ndarray, rng: np.random.Generator,
                u2: np.ndarray | None = None) -> dict[str, np.ndarray]:
    """Columnas radiométricas/geométricas plausibles (cosméticas) dada la intensidad k.

    ``u2`` fija la posición en el barrido (y por tanto scan/track); si es None se sortea.
    """
    c = _COSMETIC[sensor]
    n = k.size
    a, b, s = c["bt_main"]
    bt_main = a + b * k + rng.normal(0, s, n) - c["bt_main_night_drop"] * night
    if "bt_main_saturation" in c:
        bt_main = np.minimum(bt_main, c["bt_main_saturation"])
    a, b, s = c["bt_aux"]
    bt_aux = a + b * k + rng.normal(0, s, n)
    mu, slope, s = c["frp_log"]
    frp = np.exp(rng.normal(mu + slope * k, s))
    if u2 is None:
        u2 = rng.uniform(0, 1, n) ** 2
    scan, track = _pixel_size_km(sensor, u2)
    if sensor == "MODIS":
        a, b, s = c["conf"]
        conf = np.clip(np.round(a + b * k + rng.normal(0, s, n)), 0, 100).astype(np.int64)
    else:
        score = k + rng.normal(0, c["conf_noise"], n)
        conf = np.where(score < c["conf_low"], "l", np.where(score > c["conf_high"], "h", "n"))
    return {"bt_main": bt_main, "bt_aux": bt_aux, "frp": frp, "scan": scan, "track": track,
            "confidence": conf}


def detect(
    sat: str,
    dn: str,
    ed: dict[str, np.ndarray],
    end_day: int,
    params: SyntheticParams,
    rng: np.random.Generator,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Simula las pasadas de ``sat`` (día o noche) sobre los evento-días ``ed``.

    Devuelve (detecciones, ensayos). ``ensayos`` trae por pasada el conteo esperado
    (con y sin deriva) y el realizado, para construir la verdad.
    """
    sat_cfg = params.satellites[sat]
    sensor = params.sensors[sat_cfg.sensor]
    active = _sat_active(sat_cfg, ed["day"], end_day)
    day = ed["day"][active]
    area = ed["area_ha"][active]
    n = day.size

    nominal_h = sat_cfg.overpass_day if dn == "D" else sat_cfg.overpass_night
    hour_nodrift = nominal_h + rng.uniform(-params.overpass_jitter_h, params.overpass_jitter_h, n)
    hour = hour_nodrift + overpass_shift(sat, day, params)

    def _k(h: np.ndarray) -> np.ndarray:
        signal = area * diurnal_factor(h, params)
        return 1 / (1 + np.exp(-np.log(signal / sensor.s50_ha) / sensor.slope))

    k = _k(hour)
    months = _days_to_dt64(day).astype("datetime64[M]").astype(np.int64) % 12
    visible = sensor.coverage * (1 - np.asarray(params.cloud_prob_by_month)[months])
    p = k * visible
    p_nodrift = _k(hour_nodrift) * visible  # lo que se vería con la hora de paso nominal
    mean_n = np.clip(area / sensor.pixel_ha, 1.0, len(_LATTICE))

    hit = rng.random(n) < p
    n_det = np.zeros(n, dtype=np.int64)
    n_det[hit] = np.minimum(1 + rng.poisson(mean_n[hit] - 1), len(_LATTICE))

    trials = {"day": day, "expected": p * mean_n, "expected_nodrift": p_nodrift * mean_n,
              "realized": n_det}

    # Posición: las detecciones de una pasada ocupan píxeles vecinos de una rejilla con el
    # tamaño de píxel de esa pasada (scan x track), desplazada en bloque por el error de
    # geolocalización y por la posición del fuego dentro del píxel.
    hit_idx = np.flatnonzero(hit)
    n_hit = n_det[hit]
    rep = np.repeat(hit_idx, n_hit)
    m = rep.size
    t_rep = np.repeat(np.arange(hit_idx.size), n_hit)  # pasada (0..n_hit-1) de cada detección
    j = np.arange(m) - np.repeat(np.cumsum(n_hit) - n_hit, n_hit)  # orden dentro de la pasada
    u2 = rng.uniform(0, 1, hit_idx.size) ** 2
    scan_km, track_km = _pixel_size_km(sat_cfg.sensor, u2)
    sub = rng.uniform(-0.5, 0.5, (hit_idx.size, 2))
    shift = rng.normal(0, sensor.geoloc_sigma_km, (hit_idx.size, 2))
    dx = (_LATTICE[j, 0] + sub[t_rep, 0]) * scan_km[t_rep] + shift[t_rep, 0]
    dy = (_LATTICE[j, 1] + sub[t_rep, 1]) * track_km[t_rep] + shift[t_rep, 1]
    lat = ed["lat"][active][rep] + dy / KM_PER_DEG_LAT
    lon = ed["lon"][active][rep] + dx / (KM_PER_DEG_LAT * np.cos(np.deg2rad(lat)))

    attrs = _attributes(sat_cfg.sensor, k[rep], np.full(m, dn == "N"), rng, u2=u2[t_rep])
    dets = {"lat": lat, "lon": lon, "day_local": day[rep], "hour_local": hour[rep],
            "type": np.zeros(m, dtype=np.int64), **attrs}
    return dets, trials


def industrial_detections(
    sat: str, dn: str, days: np.ndarray, sources: np.ndarray, end_day: int,
    params: SyntheticParams, rng: np.random.Generator,
) -> dict[str, np.ndarray]:
    """Fuentes fijas (type = 2): detección casi todos los meses, en el mismo lugar."""
    sat_cfg = params.satellites[sat]
    sensor = params.sensors[sat_cfg.sensor]
    days = days[_sat_active(sat_cfg, days, end_day)]
    n_src = sources.shape[0]
    d = np.repeat(days, n_src)
    src = np.tile(np.arange(n_src), days.size)
    hit = rng.random(d.size) < params.industrial.pass_detect_prob
    d, src = d[hit], src[hit]
    m = d.size
    nominal_h = sat_cfg.overpass_day if dn == "D" else sat_cfg.overpass_night
    hour = nominal_h + rng.uniform(-params.overpass_jitter_h, params.overpass_jitter_h, m)
    hour = hour + overpass_shift(sat, d, params)
    lat0 = sources[src, 0]
    lat = lat0 + rng.normal(0, sensor.geoloc_sigma_km, m) / KM_PER_DEG_LAT
    lon = sources[src, 1] + rng.normal(0, sensor.geoloc_sigma_km, m) / (
        KM_PER_DEG_LAT * np.cos(np.deg2rad(lat0))
    )
    k = rng.uniform(*_COSMETIC["industrial_k"], m)
    attrs = _attributes(sat_cfg.sensor, k, np.full(m, dn == "N"), rng)
    return {"lat": lat, "lon": lon, "day_local": d, "hour_local": hour,
            "type": np.full(m, 2, dtype=np.int64), **attrs}


def add_bowtie(dets: dict[str, np.ndarray], params: SyntheticParams,
               rng: np.random.Generator) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Duplica ~``bowtie_fraction`` de las detecciones MODIS a < 1 km, misma pasada."""
    n = dets["lat"].size
    dup = np.flatnonzero(rng.random(n) < params.bowtie_fraction)
    dist = rng.uniform(*params.bowtie_offset_km, dup.size)
    theta = rng.uniform(0, 2 * np.pi, dup.size)
    out = {k: np.concatenate([v, v[dup]]) for k, v in dets.items()}
    out["lat"][n:] += dist * np.sin(theta) / KM_PER_DEG_LAT
    out["lon"][n:] += dist * np.cos(theta) / (KM_PER_DEG_LAT * np.cos(np.deg2rad(out["lat"][n:])))
    return out, dets["day_local"][dup]


# --------------------------------------------------------------------------------------
# Formato FIRMS
# --------------------------------------------------------------------------------------
def to_firms_frame(sat: str, dn: str, dets: dict[str, np.ndarray], utc_offset_h: float,
                   nrt_start_day: int, params: SyntheticParams) -> pd.DataFrame:
    """Convierte detecciones a las columnas exactas de FIRMS (+ claves internas _utc_year, _nrt)."""
    sat_cfg = params.satellites[sat]
    sensor = sat_cfg.sensor
    c = _COSMETIC[sensor]
    minutes_utc = np.round((dets["hour_local"] - utc_offset_h) * 60).astype(np.int64)
    day_utc = dets["day_local"] + np.floor_divide(minutes_utc, 1440)
    minutes_utc = np.mod(minutes_utc, 1440)
    hhmm = (minutes_utc // 60) * 100 + minutes_utc % 60
    dt64 = _days_to_dt64(day_utc)

    cols = MODIS_COLUMNS if sensor == "MODIS" else VIIRS_COLUMNS
    sd = c["scan_decimals"]
    frame = pd.DataFrame({
        cols[0]: np.round(dets["lat"], c["lat_decimals"]),
        cols[1]: np.round(dets["lon"], c["lat_decimals"]),
        cols[2]: np.round(dets["bt_main"], 2),
        cols[3]: np.round(dets["scan"], sd),
        cols[4]: np.round(dets["track"], sd),
        cols[5]: np.datetime_as_string(dt64, unit="D"),
        cols[6]: pd.Series(hhmm).astype(str).str.zfill(4).to_numpy(),
        cols[7]: sat_cfg.code,
        cols[8]: sensor,
        cols[9]: dets["confidence"],
        cols[10]: np.where(dets["day_local"] >= nrt_start_day, "SYN-NRT", "SYN"),
        cols[11]: np.round(dets["bt_aux"], 2),
        cols[12]: np.round(dets["frp"], c["frp_decimals"]),
        cols[13]: dn,
        cols[14]: dets["type"],
    })
    frame["_utc_year"] = dt64.astype("datetime64[Y]").astype(np.int64) + 1970
    return frame


class _CsvWriter:
    """Escribe un CSV por sensor-satélite-año(UTC)-versión, en modo append."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.rows: dict[str, int] = {}

    def write(self, sat: str, sensor: str, frame: pd.DataFrame) -> None:
        cols = MODIS_COLUMNS if sensor == "MODIS" else VIIRS_COLUMNS
        for (year, version), part in frame.groupby(["_utc_year", "version"], sort=True):
            name = f"{sensor.lower()}_{sat.lower()}_{year}_{str(version).lower()}.csv"
            # Los NRT de FIRMS no traen `type`: igual aquí.
            use_cols = [c for c in cols if not (version == "SYN-NRT" and c == "type")]
            path = self.out_dir / name
            new = name not in self.rows
            part[use_cols].to_csv(path, mode="w" if new else "a", header=new, index=False,
                                  lineterminator="\n")
            self.rows[name] = self.rows.get(name, 0) + len(part)


# --------------------------------------------------------------------------------------
# Orquestación
# --------------------------------------------------------------------------------------
def _clean_out_dir(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for pattern in ("*_syn.csv", "*_syn-nrt.csv", "truth*.parquet", "manifest.json"):
        for f in out_dir.glob(pattern):
            f.unlink()


def generate(
    settings: Settings,
    *,
    out_dir: Path | None = None,
    scale: float | None = None,
    seed: int | None = None,
    start: date | None = None,
    end: date | None = None,
) -> SynthResult:
    """Genera los CSV sintéticos, la verdad y el manifiesto. Devuelve un resumen."""
    t0 = time.perf_counter()
    params = settings.params.synthetic
    tz = settings.params.timezone
    out_dir = out_dir or settings.paths.synthetic_dir
    scale = params.scale if scale is None else scale
    seed = params.seed if seed is None else seed
    start = start or params.start
    end = end or resolve_end(params, tz)
    if end < start:
        raise ValueError(f"Rango vacio: start={start} > end={end}")

    # Flujos aleatorios independientes: cambiar un parámetro de detección no altera los
    # eventos "verdaderos" (y viceversa).
    ss_land, ss_events, ss_detect, ss_noise = np.random.SeedSequence(seed).spawn(4)
    rng_land, rng_events = np.random.default_rng(ss_land), np.random.default_rng(ss_events)
    rng_detect, rng_noise = np.random.default_rng(ss_detect), np.random.default_rng(ss_noise)
    utc_offset_h = _utc_offset_hours(tz, start, end)
    end_day = _to_day(end)
    nrt_start_day = end_day - params.nrt_days + 1
    _clean_out_dir(out_dir)
    log.info("Simulando focos %s..%s (scale=%s, seed=%s) en %s", start, end, scale, seed, out_dir)

    land = build_landscape(settings, rng_land)
    factors, extremes = annual_factors(params, start, end, rng_land)
    w, s, e, n = settings.params.region.bbox
    lo, hi = params.industrial.n_sources
    n_src = int(rng_land.integers(lo, hi + 1))
    sources = np.column_stack(
        [rng_land.uniform(s, n, n_src), rng_land.uniform(w, e, n_src)]
    )

    # Acumuladores de verdad por (satélite, día/noche, mes local).
    m_first = int(_month_index(np.array([_to_day(start)]))[0])
    n_months = int(_month_index(np.array([end_day]))[0]) - m_first + 1
    truth_keys = ("expected", "expected_nodrift", "n_vegetation", "n_industrial", "n_bowtie")
    acc = {(sat, dn): {k: np.zeros(n_months) for k in truth_keys}
           for sat in SATELLITES for dn in PASSES}

    def _add(sat: str, dn: str, key: str, days: np.ndarray, weights=None) -> None:
        idx = _month_index(days) - m_first
        acc[(sat, dn)][key] += np.bincount(idx, weights=weights, minlength=n_months)

    writer = _CsvWriter(out_dir)
    events_all = []
    next_id = 0
    for year in range(start.year, end.year + 1):
        events = simulate_events(year, start, end, factors[year], scale, land, params,
                                 rng_events, next_id)
        next_id += len(events)
        events_all.append(events)
        ed = expand_event_days(events, end_day, params, rng_events)
        y0, y1 = max(date(year, 1, 1), start), min(date(year, 12, 31), end)
        year_days = np.arange(_to_day(y0), _to_day(y1) + 1)

        for sat in SATELLITES:
            sensor = params.satellites[sat].sensor
            frames = []
            for dn in PASSES:
                dets, trials = detect(sat, dn, ed, end_day, params, rng_detect)
                _add(sat, dn, "expected", trials["day"], trials["expected"])
                _add(sat, dn, "expected_nodrift", trials["day"], trials["expected_nodrift"])
                _add(sat, dn, "n_vegetation", trials["day"], trials["realized"])

                ind = industrial_detections(sat, dn, year_days, sources, end_day, params,
                                            rng_noise)
                _add(sat, dn, "n_industrial", ind["day_local"])
                merged = {k: np.concatenate([dets[k], ind[k]]) for k in dets}
                if sensor == "MODIS":
                    merged, dup_days = add_bowtie(merged, params, rng_noise)
                    _add(sat, dn, "n_bowtie", dup_days)
                if merged["lat"].size:
                    frames.append(to_firms_frame(sat, dn, merged, utc_offset_h, nrt_start_day,
                                                 params))
            if frames:
                frame = pd.concat(frames, ignore_index=True)
                frame = frame.sort_values(["acq_date", "acq_time"], kind="stable")
                writer.write(sat, sensor, frame)
        log.info("  %d: %d eventos, %d filas acumuladas", year, len(events),
                 sum(writer.rows.values()))

    # Verdad mensual (solo meses en que el satélite estaba activo).
    month_idx = np.arange(n_months) + m_first
    years, months = month_idx // 12 + 1970, month_idx % 12 + 1
    truth_parts = []
    for (sat, dn), arrs in acc.items():
        cfg = params.satellites[sat]
        last = cfg.end or end
        first_m = (cfg.start.year - 1970) * 12 + cfg.start.month - 1
        last_m = (last.year - 1970) * 12 + last.month - 1
        active = (month_idx >= first_m) & (month_idx <= last_m)
        part = pd.DataFrame({"year": years, "month": months, "satellite": sat, "daynight": dn,
                             **arrs})[active]
        truth_parts.append(part)
    truth = pd.concat(truth_parts, ignore_index=True)
    for k in ("n_vegetation", "n_industrial", "n_bowtie"):
        truth[k] = truth[k].astype(np.int64)
    truth["n_total"] = truth["n_vegetation"] + truth["n_industrial"] + truth["n_bowtie"]
    truth.to_parquet(out_dir / "truth.parquet", index=False)

    events_df = pd.concat(events_all, ignore_index=True)
    events_df["start_date"] = _days_to_dt64(events_df.pop("start_day").to_numpy())
    events_df.to_parquet(out_dir / "truth_events.parquet", index=False)

    elapsed = time.perf_counter() - t0
    manifest = {
        "data_mode": "synthetic",
        "warning": "DATOS SINTETICOS: no representan focos reales; no usar para decisiones.",
        "generator_version": GENERATOR_VERSION,
        "firecal_version": __version__,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "seed": seed,
        "scale": scale,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "nrt_start": (EPOCH + timedelta(days=nrt_start_day)).isoformat(),
        "utc_offset_hours": utc_offset_h,
        "region": settings.params.region.model_dump(mode="json"),
        "h3_res": settings.params.grid.h3_res_store,
        "params": params.model_dump(mode="json"),
        "landscape": {"n_cells": int(land["cells"].size), "hot_zones": land["zones"]},
        "annual_factors": {str(k): round(v, 4) for k, v in factors.items()},
        "extreme_years": extremes,
        "industrial_sources": [{"lat": float(a), "lon": float(b)} for a, b in sources],
        "n_events": int(next_id),
        "files": dict(sorted(writer.rows.items())),
        "total_rows": int(sum(writer.rows.values())),
        "elapsed_s": round(elapsed, 2),
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    log.info("Listo: %d filas en %d archivos, %d eventos, %.1f s", manifest["total_rows"],
             len(writer.rows), next_id, elapsed)
    return SynthResult(out_dir, dict(writer.rows), elapsed, next_id, manifest)
