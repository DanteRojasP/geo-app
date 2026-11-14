"""Eventos armonizados del plan (alternativa A) -> Parquet particionado por año y mes.

Regla de deduplicación (PLAN.md sección 2): si MODIS y VIIRS (o dos satélites) detectan en la misma
celda de 1 km el mismo día (fecha local, America/Lima), cuenta como un solo evento y se conserva la
detección de mayor FRP (MW).

Constelación constante (hallazgo al implementar el plan): sumar todos los satélites VIIRS hace que
las detecciones suban en 2018 (entra NOAA-20) y 2024 (NOAA-21) sin que haya más fuego. Por eso se
usa UN solo VIIRS a la vez: S-NPP mientras opera y NOAA-20 después (``VIIRS_CHAIN``). MODIS usa
Terra + Aqua, y la serie empieza en ``harmonization.series_start`` (2003-01, Aqua completo).

Esquema del evento armonizado (PLAN.md sección 3):
``fecha_utc, hora, lat, lon, celda_1km, sensor, confianza_norm (0-1), frp_mw, dia_noche``
más columnas de apoyo: ``fecha_local``, ``satelite``, ``n_detecciones`` (detecciones fusionadas),
``sensores`` (p. ej. "MODIS+VIIRS"), ``departamento`` (código ISO o NULL) y las particiones
``anio``, ``mes`` (mes LOCAL).
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import shapely

from firecal.etl.load import connect
from firecal.regions import load_regions
from firecal.settings import Settings

log = logging.getLogger(__name__)

EVENTS_DIRNAME = "eventos"
META_FILENAME = "eventos_meta.json"
PLAN_VERSION = "plan-AC-v0.1"

# Confianza normalizada 0-1. MODIS ya es 0-100 -> /100. VIIRS es categórica: valores
# representativos de cada clase (supuesto documentado en /api/metadatos; ajustable).
VIIRS_CONF_NORM = {"low": 0.3, "nominal": 0.6, "high": 0.9}

# Primer mes completo con VIIRS (S-NPP desde 2012-01-20): define las eras de sensores.
VIIRS_ERA_START = (2012, 2)


def viirs_chain(settings: Settings) -> list[tuple[str, date, date | None]]:
    """[(satélite, desde, hasta)]: S-NPP hasta su fin; luego NOAA-20."""
    snpp_start, snpp_end = settings.params.harmonization.satellite_periods["SNPP"]
    return [("SNPP", snpp_start, snpp_end), ("N20", snpp_end or date.max, None)]


def constellation_mask(df: pd.DataFrame, settings: Settings) -> np.ndarray:
    """True para detecciones de la constelación constante (MODIS + un VIIRS a la vez)."""
    keep = (df["sensor"] == "MODIS").to_numpy().copy()
    d = pd.to_datetime(df["local_date"])
    for sat, start, end in viirs_chain(settings):
        m = (df["satellite"] == sat) & (d >= pd.Timestamp(start))
        if end is not None:
            m &= d < pd.Timestamp(end)
        keep |= m.to_numpy()
    y0, m0 = (int(v) for v in settings.params.harmonization.series_start.split("-"))
    keep &= (d >= pd.Timestamp(y0, m0, 1)).to_numpy()
    return keep


def events_dir(settings: Settings) -> Path:
    return settings.paths.processed_dir / EVENTS_DIRNAME


def meta_path(settings: Settings) -> Path:
    return settings.paths.processed_dir / META_FILENAME


def confidence_norm(df: pd.DataFrame) -> np.ndarray:
    """Confianza en 0-1: MODIS numérica / 100; VIIRS por categoría (``VIIRS_CONF_NORM``)."""
    out = np.full(len(df), np.nan)
    modis = (df["sensor"] == "MODIS").to_numpy()
    raw = pd.to_numeric(df["confidence_raw"], errors="coerce").to_numpy()
    out[modis] = np.clip(raw[modis] / 100.0, 0, 1)
    viirs = ~modis
    out[viirs] = df.loc[viirs, "confidence_cat"].map(VIIRS_CONF_NORM).to_numpy(dtype=float)
    return np.round(out, 2)


def assign_departments(lat: np.ndarray, lon: np.ndarray, settings: Settings) -> np.ndarray:
    """Código de departamento (``level == "departamento"``) que contiene cada punto, o None."""
    out = np.full(lat.size, None, dtype=object)
    for region in load_regions(settings.paths.regions_dir).values():
        if region.level != "departamento":
            continue
        shapely.prepare(region.geometry)
        inside = shapely.contains_xy(region.geometry, lon, lat) & pd.isna(out)
        out[inside] = region.code
    return out


def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Un evento por (celda_1km, fecha local): la detección de mayor FRP (FRP nulo = 0)."""
    df = df.assign(_frp=df["frp"].fillna(0.0))
    grp = df.groupby(["px1km_id", "local_date"], sort=False)
    n_det = grp["id"].transform("size")
    mixed = grp["sensor"].transform("nunique") > 1
    sensors = df["sensor"].where(~mixed, "MODIS+VIIRS")
    df = df.assign(n_detecciones=n_det, sensores=sensors)
    df = df.sort_values(["px1km_id", "local_date", "_frp", "id"],
                        ascending=[True, True, False, True])
    return df.drop_duplicates(["px1km_id", "local_date"], keep="first").drop(columns="_frp")


def build_events(settings: Settings) -> dict:
    """``hotspots_clean`` (DuckDB) -> eventos armonizados en Parquet particionado (anio, mes)."""
    with connect(settings.paths.duckdb_path) as con:
        df = con.execute(
            "SELECT id, sensor, satellite, acq_utc, local_date, lat, lon, confidence_cat, "
            "confidence_raw, frp, daynight, px1km_id FROM hotspots_clean").df()
        info = dict(con.execute("SELECT key, value FROM pipeline_info").fetchall())
    n_all = len(df)
    df = df[constellation_mask(df, settings)]
    n_in = len(df)
    df = deduplicate(df)
    acq = pd.to_datetime(df["acq_utc"])
    local = pd.to_datetime(df["local_date"])
    ev = pd.DataFrame({
        "fecha_utc": acq.dt.date,
        "hora": acq.dt.strftime("%H:%M"),
        "lat": df["lat"].round(5),
        "lon": df["lon"].round(5),
        "celda_1km": df["px1km_id"].astype("int64"),
        "sensor": df["sensor"],
        "satelite": df["satellite"],
        "confianza_norm": confidence_norm(df),
        "frp_mw": df["frp"].round(2),
        "dia_noche": df["daynight"],
        "fecha_local": local.dt.date,
        "n_detecciones": df["n_detecciones"].astype("int32"),
        "sensores": df["sensores"],
    })
    ev["departamento"] = assign_departments(ev["lat"].to_numpy(), ev["lon"].to_numpy(), settings)
    ev["anio"] = local.dt.year.astype("int32")
    ev["mes"] = local.dt.month.astype("int32")

    out = events_dir(settings)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    with connect(settings.paths.duckdb_path) as con:
        con.register("_ev", ev)
        con.execute("COPY (SELECT * FROM _ev ORDER BY anio, mes, departamento) "
                    f"TO '{out.as_posix()}' "
                    "(FORMAT parquet, PARTITION_BY (anio, mes), COMPRESSION zstd)")
        con.unregister("_ev")

    y0 = int(ev["anio"].min())
    meta = {
        "plan_version": PLAN_VERSION,
        "data_mode": info.get("data_mode", settings.data_mode),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "n_detecciones_limpias": int(n_all),
        "n_detecciones_constelacion": int(n_in),
        "viirs_cadena": [[s, str(a), None if b is None else str(b)]
                         for s, a, b in viirs_chain(settings)],
        "n_eventos": int(len(ev)),
        "fusionadas": int(n_in - len(ev)),
        "eventos_multisensor": int((ev["sensores"] == "MODIS+VIIRS").sum()),
        "primer_mes": f"{y0}-{int(ev.loc[ev['anio'] == y0, 'mes'].min()):02d}",
        "ultimo_fecha_local": str(ev["fecha_local"].max()),
        "umbral_confianza": settings.params.filters.min_confidence,
        "grilla_deg": settings.params.grid.px1km_deg,
        "viirs_conf_norm": VIIRS_CONF_NORM,
        "departamentos": sorted(c for c in ev["departamento"].dropna().unique()),
    }
    meta_path(settings).write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    log.info("Eventos del plan: %d detecciones -> %d eventos (%s)", n_in, len(ev), out)
    return meta
