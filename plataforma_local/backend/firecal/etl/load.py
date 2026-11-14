"""Escritura y lectura de tablas del pipeline en DuckDB (``data/processed/firecal.duckdb``)."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

log = logging.getLogger(__name__)

# Tipos explícitos de las tablas de focos (DuckDB). TIMESTAMP en UTC, sin zona.
HOTSPOT_TYPES = {
    "id": "BIGINT", "sensor": "VARCHAR", "satellite": "VARCHAR", "acq_utc": "TIMESTAMP",
    "local_date": "DATE", "lat": "DOUBLE", "lon": "DOUBLE", "confidence_cat": "VARCHAR",
    "confidence_raw": "VARCHAR", "frp": "DOUBLE", "daynight": "VARCHAR", "type": "INTEGER",
    "version": "VARCHAR", "source_file": "VARCHAR", "h3_7": "VARCHAR", "px1km_id": "BIGINT",
    "is_static": "BOOLEAN",
}


@contextmanager
def connect(db_path: Path, read_only: bool = False):
    """Conexión a DuckDB que se cierra siempre (importante en Windows: libera el archivo)."""
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    elif not db_path.is_file():
        raise FileNotFoundError(f"No existe la base de datos {db_path}")
    con = duckdb.connect(str(db_path), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def write_table(con: duckdb.DuckDBPyConnection, name: str, df: pd.DataFrame,
                types: dict[str, str] | None = None) -> None:
    """Reemplaza la tabla ``name`` con el contenido de ``df`` (con casts explícitos)."""
    types = types or {}
    select = ", ".join(
        f'CAST("{c}" AS {types[c]}) AS "{c}"' if c in types else f'"{c}"' for c in df.columns
    )
    con.register("_df", df)
    try:
        # fetchall(): DuckDB 2 exige consumir el resultado antes de otra operacion
        con.execute(f'CREATE OR REPLACE TABLE "{name}" AS SELECT {select} FROM _df').fetchall()
    finally:
        con.unregister("_df")
    log.info("Tabla %s: %d filas", name, len(df))


def set_info(con: duckdb.DuckDBPyConnection, **values: str) -> None:
    """Guarda metadatos del pipeline (modo de datos, fechas de cada paso) en ``pipeline_info``."""
    con.execute("CREATE TABLE IF NOT EXISTS pipeline_info (key VARCHAR PRIMARY KEY, value VARCHAR)"
                ).fetchall()
    for key, value in values.items():
        sql = "INSERT OR REPLACE INTO pipeline_info VALUES (?, ?)"
        con.execute(sql, [key, str(value)]).fetchall()


def read_table(con: duckdb.DuckDBPyConnection, name: str) -> pd.DataFrame:
    return con.execute(f'SELECT * FROM "{name}"').df()
