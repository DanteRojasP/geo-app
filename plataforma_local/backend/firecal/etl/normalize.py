"""Normalización de un CSV de FIRMS (MODIS o VIIRS) al esquema de la tabla ``hotspots``.

- ``acq_date`` + ``acq_time`` (HHMM UTC, con o sin ceros a la izquierda) -> ``acq_utc``.
- ``local_date`` en la zona horaria del proyecto (America/Lima).
- Confianza: MODIS 0-100 -> low/nominal/high según ``filters.modis_confidence_bins``;
  VIIRS l/n/h -> low/nominal/high.
- Satélite: código del CSV -> TERRA/AQUA/SNPP/N20/N21 (ver ``firms_schema.FIRMS_ASSUMPTIONS``);
  códigos desconocidos se registran en el log y sus filas se descartan.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from firecal.etl.firms_schema import FIRMS_ASSUMPTIONS, Sensor, classify_version

log = logging.getLogger(__name__)

# Columnas de salida (en orden). `id`, `h3_7`, `px1km_id` e `is_static` se agregan después.
NORMALIZED_COLUMNS = [
    "sensor", "satellite", "acq_utc", "local_date", "lat", "lon", "confidence_cat",
    "confidence_raw", "frp", "daynight", "type", "version", "source_file",
]


def acq_time_minutes(raw: pd.Series) -> pd.Series:
    """HHMM (UTC, con o sin ceros a la izquierda: '552' = 05:52) -> minutos desde las 00:00.

    NaN si no es una hora válida (no numérica, decimales, HH >= 24 o MM >= 60).
    """
    v = pd.to_numeric(raw.astype("string").str.strip(), errors="coerce").astype(float)
    ok = v.notna() & (v == np.floor(v)) & (v >= 0) & (v < 2400) & ((v % 100) < 60)
    return ((v // 100) * 60 + v % 100).where(ok)


def parse_dates(raw: pd.Series) -> pd.Series:
    """'YYYY-MM-DD' -> datetime64; se parsea cada fecha distinta una sola vez (rápido)."""
    s = raw.astype("string").str.strip()
    uniq = s.dropna().unique()
    parsed = pd.Series(pd.to_datetime(uniq, format="%Y-%m-%d", errors="coerce"), index=uniq)
    return s.map(parsed)


def modis_confidence_category(conf: pd.Series, bins: tuple[int, int]) -> pd.Series:
    """MODIS 0-100 -> low (< bins[0]) | nominal | high (>= bins[1])."""
    values = pd.to_numeric(conf, errors="coerce")
    cat = np.select([values < bins[0], values < bins[1], values >= bins[1]],
                    ["low", "nominal", "high"], default=None)
    return pd.Series(cat, index=conf.index, dtype="string")


def viirs_confidence_category(conf: pd.Series) -> pd.Series:
    mapping = FIRMS_ASSUMPTIONS["viirs_confidence"]
    return conf.astype("string").str.strip().str.lower().map(mapping).astype("string")


def map_satellite(sensor: Sensor, codes: pd.Series, source_file: str) -> pd.Series:
    """Código del CSV -> satélite normalizado. Registra en el log los códigos desconocidos."""
    table = {code: sat for (sen, code), sat in FIRMS_ASSUMPTIONS["satellite_codes"].items()
             if sen == sensor}
    clean = codes.astype("string").str.strip()
    mapped = clean.map(table)
    unknown = clean[mapped.isna()].value_counts(dropna=False)
    for code, n in unknown.items():
        log.warning("Codigo de satelite desconocido %r (%s) en %s: %d filas descartadas",
                    code, sensor, source_file, n)
    return mapped.astype("string")


def normalize_frame(raw: pd.DataFrame, sensor: Sensor, source_file: str, *, timezone: str,
                    modis_bins: tuple[int, int]) -> pd.DataFrame:
    """Convierte un DataFrame crudo de FIRMS al esquema normalizado (sin id ni celdas)."""
    n_in = len(raw)
    out = pd.DataFrame(index=raw.index)
    out["sensor"] = sensor
    out["satellite"] = map_satellite(sensor, raw["satellite"], source_file)

    minutes = acq_time_minutes(raw["acq_time"])
    bad_time = minutes.isna()
    if bad_time.any():
        log.warning("%s: %d filas con acq_time invalido descartadas", source_file,
                    int(bad_time.sum()))
    acq = (parse_dates(raw["acq_date"]) + pd.to_timedelta(minutes, unit="min")).dt.tz_localize(
        "UTC")
    out["acq_utc"] = acq.dt.tz_localize(None)  # se guarda como TIMESTAMP en UTC
    out["local_date"] = acq.dt.tz_convert(timezone).dt.tz_localize(None).dt.normalize()

    out["lat"] = pd.to_numeric(raw["latitude"], errors="coerce")
    out["lon"] = pd.to_numeric(raw["longitude"], errors="coerce")
    out["confidence_raw"] = raw["confidence"].astype("string").str.strip()
    if sensor == "MODIS":
        out["confidence_cat"] = modis_confidence_category(raw["confidence"], modis_bins)
    else:
        out["confidence_cat"] = viirs_confidence_category(raw["confidence"])
    out["frp"] = pd.to_numeric(raw["frp"], errors="coerce")
    out["daynight"] = raw["daynight"].astype("string").str.strip().str.upper()
    out["type"] = (pd.to_numeric(raw["type"], errors="coerce").astype("Int64")
                   if "type" in raw.columns else pd.Series(pd.NA, index=raw.index, dtype="Int64"))
    versions = {v: classify_version(v) for v in raw["version"].dropna().unique()}
    out["version"] = raw["version"].map(versions).astype("string")
    out["source_file"] = source_file

    valid = (
        out["satellite"].notna() & out["acq_utc"].notna() & out["lat"].between(-90, 90)
        & out["lon"].between(-180, 180) & out["confidence_cat"].notna()
        & out["daynight"].isin(FIRMS_ASSUMPTIONS["daynight_values"])
    )
    dropped = n_in - int(valid.sum())
    if dropped:
        log.warning("%s: %d de %d filas descartadas por valores invalidos", source_file,
                    dropped, n_in)
    return out.loc[valid, NORMALIZED_COLUMNS].reset_index(drop=True)
