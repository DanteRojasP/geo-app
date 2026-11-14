"""Lectura de CSV de FIRMS (archivo histórico o sintéticos) con detección de esquema.

El esquema (MODIS o VIIRS) se detecta por las columnas, no por el nombre del archivo.
Los archivos que no encajan en ningún esquema se registran en el log y se ignoran.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from firecal.etl.firms_schema import REQUIRED_COLUMNS, SCHEMA_SIGNATURE, Sensor
from firecal.etl.normalize import NORMALIZED_COLUMNS, normalize_frame
from firecal.settings import Settings

log = logging.getLogger(__name__)

# Se leen como texto para no perder ceros a la izquierda ni mezclar tipos (l/n/h vs 0-100).
_TEXT_COLUMNS = {"acq_date": "string", "acq_time": "string", "satellite": "string",
                 "confidence": "string", "version": "string", "daynight": "string",
                 "instrument": "string"}


def detect_schema(columns: list[str] | set[str]) -> Sensor | None:
    """'MODIS' o 'VIIRS' según las columnas; None si no corresponde a ninguno."""
    cols = {c.strip().lower() for c in columns}
    if not cols >= REQUIRED_COLUMNS:
        return None
    matches = [sensor for sensor, sig in SCHEMA_SIGNATURE.items() if sig <= cols]
    return matches[0] if len(matches) == 1 else None


def read_firms_csv(path: Path, *, timezone: str,
                   modis_bins: tuple[int, int]) -> pd.DataFrame | None:
    """Lee y normaliza un CSV. Devuelve None si el esquema no se reconoce."""
    header = pd.read_csv(path, nrows=0).columns
    sensor = detect_schema(list(header))
    if sensor is None:
        log.warning("%s: columnas no reconocidas como MODIS ni VIIRS; se ignora. Columnas: %s",
                    path.name, list(header))
        return None
    text_cols = {c: t for c, t in _TEXT_COLUMNS.items() if c in header}
    raw = pd.read_csv(path, dtype=text_cols, engine="pyarrow")
    raw.columns = [c.strip().lower() for c in raw.columns]
    return normalize_frame(raw, sensor, path.name, timezone=timezone, modis_bins=modis_bins)


def find_csv_files(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.rglob("*.csv") if p.is_file())


def load_archive(settings: Settings, input_dir: Path | None = None) -> pd.DataFrame:
    """Lee todos los CSV de la carpeta de entrada del modo actual y los normaliza.

    Modo ``synthetic`` -> ``data/synthetic/``; modo ``real`` -> ``data/raw/firms/``.
    Nunca se mezclan ambas carpetas. Devuelve las filas ordenadas con un ``id`` estable.
    """
    input_dir = input_dir or settings.input_dir
    if not input_dir.is_dir():
        raise FileNotFoundError(
            f"No existe la carpeta de entrada {input_dir} (modo {settings.data_mode}). "
            + ("Ejecuta primero: firecal synth" if settings.data_mode == "synthetic"
               else "Coloca ahi los CSV descargados de FIRMS.")
        )
    files = find_csv_files(input_dir)
    if not files:
        raise FileNotFoundError(f"No hay archivos CSV en {input_dir}")

    p = settings.params
    frames = []
    for path in files:
        df = read_firms_csv(path, timezone=p.timezone, modis_bins=p.filters.modis_confidence_bins)
        if df is not None and len(df):
            frames.append(df)
            log.debug("%s: %d filas", path.name, len(df))
    if not frames:
        raise ValueError(f"Ningun CSV de {input_dir} tiene un esquema FIRMS reconocible")
    out = pd.concat(frames, ignore_index=True)
    out = out.sort_values(["acq_utc", "satellite", "lat", "lon"], kind="stable",
                          ignore_index=True)
    out.insert(0, "id", range(1, len(out) + 1))
    log.info("Leidos %d archivos de %s: %d filas normalizadas", len(frames), input_dir,
             len(out))
    return out[["id", *NORMALIZED_COLUMNS]]
