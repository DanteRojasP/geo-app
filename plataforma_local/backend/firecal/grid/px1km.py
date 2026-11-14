"""Rejilla regular de ~1 km (``grid.px1km_deg``) para contar píxeles distintos y fuentes fijas.

``px1km_id`` es un entero: fila (desde -90°) x número de columnas + columna (desde -180°).
"""

from __future__ import annotations

import numpy as np


def _n_cols(deg: float) -> int:
    return int(round(360.0 / deg))


def px1km_id(lat: np.ndarray, lon: np.ndarray, deg: float) -> np.ndarray:
    """Identificador entero de la celda regular de ``deg`` grados que contiene cada punto."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    row = np.floor((lat + 90.0) / deg).astype(np.int64)
    col = np.floor((lon + 180.0) / deg).astype(np.int64)
    return row * _n_cols(deg) + col


def px1km_center(ids: np.ndarray, deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Centro (lat, lon) de cada celda."""
    ids = np.asarray(ids, dtype=np.int64)
    row, col = np.divmod(ids, _n_cols(deg))
    return -90.0 + (row + 0.5) * deg, -180.0 + (col + 0.5) * deg
