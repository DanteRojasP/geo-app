"""Utilidades H3 (API v4 de la librería ``h3``; nombres verificados con ``dir(h3)``)."""

from __future__ import annotations

import h3
import numpy as np
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry


def latlng_to_cells(lat: np.ndarray, lon: np.ndarray, res: int) -> np.ndarray:
    """Celda H3 (texto hexadecimal) de cada punto."""
    f = h3.latlng_to_cell
    return np.array([f(a, b, res) for a, b in zip(np.asarray(lat).tolist(),
                                                  np.asarray(lon).tolist(), strict=True)],
                    dtype=object)


def parents(cells, res: int) -> dict[str, str]:
    """Celda padre en ``res`` para cada celda distinta."""
    return {c: h3.cell_to_parent(c, res) for c in set(cells)}


def _shapely_to_h3shape(geom: BaseGeometry) -> h3.H3Shape:
    def poly(p: Polygon) -> h3.LatLngPoly:
        outer = [(y, x) for x, y in p.exterior.coords[:-1]]
        holes = [[(y, x) for x, y in ring.coords[:-1]] for ring in p.interiors]
        return h3.LatLngPoly(outer, *holes)

    if isinstance(geom, Polygon):
        return poly(geom)
    if isinstance(geom, MultiPolygon):
        return h3.LatLngMultiPoly(*[poly(p) for p in geom.geoms])
    raise TypeError(f"Geometria no soportada para H3: {geom.geom_type}")


def polygon_cells(geom: BaseGeometry, res: int) -> set[str]:
    """Celdas H3 cuyo centro cae dentro de la geometría (criterio de ``h3.polygon_to_cells``)."""
    return set(h3.polygon_to_cells(_shapely_to_h3shape(geom), res))


def cell_centers(cells) -> tuple[np.ndarray, np.ndarray]:
    """(lat, lon) del centro de cada celda."""
    pts = np.array([h3.cell_to_latlng(c) for c in cells], dtype=float).reshape(-1, 2)
    return pts[:, 0], pts[:, 1]
