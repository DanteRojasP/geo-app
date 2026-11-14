"""Acceso a datos de la API, encapsulado en ``Repository``.

Los routers y servicios solo hablan con ``Repository``: para pasar a PostGIS más adelante basta
con otra implementación de esta clase.

Implementación actual (DuckDB):
- Las tablas pequeñas/medianas (celdas, regiones, serie armonizada, conteos diurnos, réplicas del
  bootstrap) se cargan en memoria al primer uso y se recargan si el archivo de la base cambia.
- Los focos individuales (``/hotspots``) se consultan en DuckDB con prefiltro por bbox y fechas.
- No se mantiene ninguna conexión abierta: así el pipeline puede reescribir la base (en Windows un
  archivo abierto queda bloqueado).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import shapely.wkt
from shapely.geometry.base import BaseGeometry

from firecal.climatology.aoi import HarmonizedData
from firecal.etl.load import connect
from firecal.settings import Settings

log = logging.getLogger(__name__)

REQUIRED_TABLES = ("cells", "regions", "harmonized_monthly", "harmonized_months",
                   "monthly_counts", "harmonization_bootstrap", "harmonization_params",
                   "hotspots")


class DataNotReady(RuntimeError):
    """La base de datos no existe o le faltan tablas del pipeline."""


@dataclass(frozen=True)
class RegionRecord:
    code: str
    name: str
    level: str
    geometry: BaseGeometry
    area_km2: float


class Repository:
    """Repositorio de solo lectura sobre ``data/processed/firecal.duckdb``."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path: Path = settings.paths.duckdb_path
        self._lock = threading.Lock()
        self._mtime: float | None = None
        # Se llenan en _load()
        self.info: dict[str, str] = {}
        self.cells: pd.DataFrame = pd.DataFrame()
        self.regions: dict[str, RegionRecord] = {}
        self.region_cells: dict[str, np.ndarray] = {}
        self.data: HarmonizedData | None = None
        self.params: pd.DataFrame = pd.DataFrame()
        self.coverage: pd.DataFrame = pd.DataFrame()
        self.cell_values: pd.DataFrame = pd.DataFrame()

    # ----------------------------------------------------------------------------------
    # Carga
    # ----------------------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        try:
            self.ensure_loaded()
            return True
        except DataNotReady:
            return False

    def ensure_loaded(self) -> None:
        """Carga (o recarga si cambió el archivo) las tablas en memoria."""
        if not self.db_path.is_file():
            raise DataNotReady(
                "No existe la base de datos. Ejecuta el pipeline: firecal all --mode synthetic "
                "(o synth, ingest, build, validate)."
            )
        mtime = self.db_path.stat().st_mtime
        if self._mtime == mtime and self.data is not None:
            return
        with self._lock:
            if self._mtime != mtime or self.data is None:
                self._load()
                self._mtime = mtime

    def _load(self) -> None:
        hp = self.settings.params.harmonization
        with connect(self.db_path, read_only=True) as con:
            tables = {r[0] for r in con.execute(
                "SELECT table_name FROM information_schema.tables").fetchall()}
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if missing:
                raise DataNotReady(f"Faltan tablas del pipeline: {missing}. Ejecuta firecal build.")
            info = (dict(con.execute("SELECT key, value FROM pipeline_info").fetchall())
                    if "pipeline_info" in tables else {})
            cells = con.execute("SELECT h3, parent_calib, region_codes, lat, lon FROM cells").df()
            regions = con.execute("SELECT * FROM regions").df()
            harmonized = con.execute(
                "SELECT h3, year, month, value, p10, p90, raw_value, source, pair, estrato "
                "FROM harmonized_monthly").df()
            months = con.execute("SELECT * FROM harmonized_months ORDER BY year, month").df()
            raw = con.execute(
                "SELECT h3, year, month, satellite, n_focos FROM monthly_counts "
                "WHERE daynight = 'D'").df()
            boot_df = con.execute("SELECT pair, estrato, rep, ratio FROM harmonization_bootstrap "
                                  "ORDER BY pair, estrato, rep").df()
            err = (con.execute("SELECT * FROM harmonization_band_error").df()
                   if "harmonization_band_error" in tables else pd.DataFrame())
            self.params = con.execute("SELECT * FROM harmonization_params").df()
            self.coverage = (con.execute("SELECT * FROM satellite_coverage").df()
                             if "satellite_coverage" in tables else pd.DataFrame())

        boot: dict[str, dict[str, np.ndarray]] = {}
        for (pair, estrato), g in boot_df.groupby(["pair", "estrato"], sort=False):
            boot.setdefault(pair, {})[estrato] = g["ratio"].to_numpy()
        errors = {}
        if not err.empty:
            for pair, g in err[err["applied"].astype(bool)].groupby("pair"):
                errors[pair] = g.sort_values("pred_lo").reset_index(drop=True)
        months["pair"] = months["pair"].where(months["pair"].notna(), None)
        harmonized["pair"] = harmonized["pair"].where(harmonized["pair"].notna(), None)
        # h3 categórica con las mismas categorías en todas las tablas: filtros por AOI rápidos.
        cats = pd.CategoricalDtype(sorted(set(cells["h3"]) | set(harmonized["h3"])
                                          | set(raw["h3"])))
        harmonized["h3"] = harmonized["h3"].astype(cats)
        raw["h3"] = raw["h3"].astype(cats)

        self.info = info
        self.cells = cells
        self.regions = {
            r.code: RegionRecord(r.code, r.name, r.level, shapely.wkt.loads(r.geom_wkt),
                                 float(r.area_km2))
            for r in regions.itertuples()
        }
        self.region_cells = {
            code: cells.loc[cells["region_codes"].map(lambda c, k=code: k in list(c)),
                            "h3"].to_numpy()
            for code in self.regions
        }
        self.cell_values = harmonized[["h3", "year", "month", "value", "p10", "p90", "raw_value",
                                       "source"]]
        self.data = HarmonizedData(
            harmonized=harmonized[["h3", "year", "month", "value", "raw_value", "pair",
                                   "estrato"]],
            months=months, raw=raw, boot=boot, error_models=errors, hp=hp)
        log.info("Repository: %d celdas, %d filas armonizadas, %d meses, modo %s",
                 len(cells), len(harmonized), len(months), self.data_mode)

    # ----------------------------------------------------------------------------------
    # Metadatos
    # ----------------------------------------------------------------------------------
    @property
    def data_mode(self) -> str:
        """Modo con el que se generaron los datos (grabado por el pipeline)."""
        return self.info.get("data_mode", self.settings.data_mode)

    @property
    def data_version(self) -> str:
        return self.info.get("data_version", self.settings.params.harmonization.data_version)

    @property
    def last_update(self) -> str | None:
        return self.info.get("harmonized_at") or self.info.get("ingested_at")

    @property
    def db_modified(self) -> str | None:
        if self._mtime is None:
            return None
        return datetime.fromtimestamp(self._mtime, UTC).isoformat(timespec="seconds")

    @property
    def cache_key(self) -> str:
        return f"{self.data_version}|{self._mtime}"

    def validation_metrics(self) -> dict | None:
        path = self.settings.paths.reports_dir / "harmonization_metrics.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def forecast_metadata(self) -> dict | None:
        path = self.settings.paths.artifacts_dir / "metadata.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def last_month(self) -> tuple[int, int]:
        m = self.data.months.iloc[-1]
        return int(m["year"]), int(m["month"])

    # ----------------------------------------------------------------------------------
    # Consultas
    # ----------------------------------------------------------------------------------
    def known_cells(self) -> np.ndarray:
        return self.cells["h3"].to_numpy()

    def cell_month_values(self, cells, year: int, month: int) -> pd.DataFrame:
        cv = self.cell_values
        sel = (cv["year"] == year) & (cv["month"] == month) & cv["h3"].isin(cells)
        return cv[sel]

    def hotspots(self, bbox: tuple[float, float, float, float], start: date,
                 end: date) -> pd.DataFrame:
        """Focos limpios (sin fuentes fijas) en el bbox y rango de fechas locales."""
        w, s, e, n = bbox
        sql = """
            SELECT id, sensor, satellite, acq_utc, local_date, lat, lon, confidence_cat,
                   confidence_raw, frp, daynight, type, version, h3_7
            FROM hotspots_clean
            WHERE lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?
              AND local_date BETWEEN ? AND ?
            ORDER BY acq_utc, id
        """
        with connect(self.db_path, read_only=True) as con:
            return con.execute(sql, [w, e, s, n, start, end]).df()
