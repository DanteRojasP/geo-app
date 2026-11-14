"""Agregación mensual (Fase 3).

- Asigna ``h3_7`` (celda H3 de almacenamiento) a cada foco de ``hotspots``.
- ``monthly_counts``: por (h3, año, mes LOCAL, satélite, día/noche) -> ``n_focos`` y
  ``n_px1km`` (píxeles ~1 km distintos con al menos un foco), solo con ``hotspots_clean``
  (sin fuentes fijas). ``is_provisional`` = ese satélite tiene datos NRT en ese mes.
- ``cells``: universo de celdas H3 de almacenamiento (las de las regiones + las que tienen focos),
  con su padre de calibración y las regiones a las que pertenecen. Las celdas sin focos
  importan: un mes sin focos en una celda es un 0, no un dato faltante.
- ``regions``: regiones de ``config/regions/``.
- ``satellite_coverage``: primer y último mes con datos por satélite y desde cuándo hay NRT.
  Sirve para distinguir "0 focos" de "satélite no operaba".

Las tablas son dispersas: una combinación (celda, mes, satélite) sin focos no tiene fila.
"""

from __future__ import annotations

import logging

import duckdb
import numpy as np
import pandas as pd
import shapely

from firecal.grid.h3_utils import cell_centers, latlng_to_cells, parents, polygon_cells
from firecal.regions import Region

log = logging.getLogger(__name__)

MONTHLY_COUNTS_SQL = """
CREATE OR REPLACE TABLE monthly_counts AS
WITH base AS (
    SELECT h3_7 AS h3, CAST(year(local_date) AS INTEGER) AS year,
           CAST(month(local_date) AS INTEGER) AS month, satellite, daynight, px1km_id,
           version LIKE '%NRT' AS is_nrt
    FROM hotspots_clean
),
prov AS (
    SELECT satellite, year, month, bool_or(is_nrt) AS is_provisional
    FROM base GROUP BY satellite, year, month
)
SELECT b.h3, b.year, b.month, b.satellite, b.daynight,
       CAST(count(*) AS INTEGER) AS n_focos,
       CAST(count(DISTINCT b.px1km_id) AS INTEGER) AS n_px1km,
       p.is_provisional
FROM base b JOIN prov p USING (satellite, year, month)
GROUP BY b.h3, b.year, b.month, b.satellite, b.daynight, p.is_provisional
ORDER BY b.year, b.month, b.satellite, b.daynight, b.h3
"""

COVERAGE_SQL = """
CREATE OR REPLACE TABLE satellite_coverage AS
SELECT satellite,
       min(year * 100 + month) AS first_yyyymm,
       max(year * 100 + month) AS last_yyyymm,
       min(CASE WHEN is_provisional THEN year * 100 + month END) AS nrt_from_yyyymm
FROM monthly_counts GROUP BY satellite ORDER BY satellite
"""


def assign_h3(con: duckdb.DuckDBPyConnection, res: int) -> int:
    """Llena ``hotspots.h3_7`` (todas las filas, incluidas las fuentes fijas)."""
    pts = con.execute("SELECT id, lat, lon FROM hotspots").df()
    pts["h3_7"] = latlng_to_cells(pts["lat"].to_numpy(), pts["lon"].to_numpy(), res)
    con.register("_h3", pts[["id", "h3_7"]])
    try:
        con.execute("UPDATE hotspots SET h3_7 = _h3.h3_7 FROM _h3 WHERE hotspots.id = _h3.id")
    finally:
        con.unregister("_h3")
    log.info("h3 res %d asignado a %d focos", res, len(pts))
    return len(pts)


def build_regions_table(con: duckdb.DuckDBPyConnection, regions: dict[str, Region]) -> None:
    df = pd.DataFrame([{"code": r.code, "name": r.name, "level": r.level,
                        "geom_wkt": r.geometry.wkt, "area_km2": r.area_km2}
                       for r in regions.values()])
    con.register("_regions", df)
    try:
        con.execute("CREATE OR REPLACE TABLE regions AS SELECT * FROM _regions ORDER BY code")
    finally:
        con.unregister("_regions")


def build_cells_table(con: duckdb.DuckDBPyConnection, regions: dict[str, Region], res: int,
                      parent_res: int) -> int:
    """Universo de celdas: las de cada región (centro dentro) + las que tienen focos."""
    cells: set[str] = set()
    for region in regions.values():
        cells |= polygon_cells(region.geometry, res)
    with_data = {r[0] for r in con.execute(
        "SELECT DISTINCT h3_7 FROM hotspots WHERE h3_7 IS NOT NULL").fetchall()}
    cells |= with_data
    ordered = sorted(cells)
    lat, lon = cell_centers(ordered)
    region_codes = [[] for _ in ordered]
    for region in regions.values():
        geom = region.geometry
        shapely.prepare(geom)
        inside = shapely.contains_xy(geom, lon, lat)
        for i in np.flatnonzero(inside):
            region_codes[i].append(region.code)
    parent = parents(ordered, parent_res)
    df = pd.DataFrame({"h3": ordered, "parent_calib": [parent[c] for c in ordered],
                       "region_codes": region_codes, "lat": lat, "lon": lon})
    con.register("_cells", df)
    try:
        con.execute("CREATE OR REPLACE TABLE cells AS SELECT h3, parent_calib, "
                    "CAST(region_codes AS VARCHAR[]) AS region_codes, lat, lon FROM _cells")
    finally:
        con.unregister("_cells")
    log.info("cells: %d celdas H3 res %d (%d con focos)", len(df), res, len(with_data))
    return len(df)


def build_monthly_counts(con: duckdb.DuckDBPyConnection) -> int:
    con.execute(MONTHLY_COUNTS_SQL)
    con.execute(COVERAGE_SQL)
    n = con.execute("SELECT count(*) FROM monthly_counts").fetchall()[0][0]
    log.info("monthly_counts: %d filas", n)
    return int(n)
