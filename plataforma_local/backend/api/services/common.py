"""Piezas comunes de los servicios: resolución del AOI, envoltura de respuesta y avisos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import numpy as np
from shapely.geometry import Point, box, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from api.db import Repository
from api.schemas import AOI, BBoxAOI, GeoJSONAOI, PointAOI, RegionAOI
from firecal.grid.h3_utils import latlng_to_cells, polygon_cells
from firecal.regions import buffer_km, geodesic_area_km2

UNIT_HARMONIZED = "focos equivalentes MODIS-Aqua (diurno)"
NOTE_SYNTHETIC = "Datos sintéticos: no usar para decisiones."
NOTE_H3 = "Bordes del AOI aproximados por celdas H3 (res 7, ~5 km²)."
NOTE_ANDES = ("Omisión de fuegos pequeños en zonas altoandinas: el producto mide actividad de "
              "quema detectable por satélite, no número de incendios.")
NOTE_DIURNAL = "Solo pasadas diurnas: las detecciones nocturnas no entran al calendario."
NOTE_PROVISIONAL = "Meses provisionales (NRT): pueden cambiar cuando lleguen los datos definitivos."
NOTE_LOW_CONF = ("Meses de baja confianza (p. ej. 2000-2002, Terra ajustado a Aqua) marcados con "
                 "low_confidence.")
NOTE_RELIABILITY_LOW = ("Confiabilidad baja: el AOI tiene muy pocos focos esperados por año; el "
                        "error relativo mensual típico supera ~50 %. Usar solo como referencia.")
NOTE_OUTSIDE = "El AOI no cubre celdas con datos de la región procesada."


class AOIError(ValueError):
    """Error de validación del AOI (se responde con 422 y este mensaje)."""


@dataclass
class ResolvedAOI:
    kind: str
    geometry: BaseGeometry
    area_km2: float
    cells: np.ndarray
    region_code: str | None = None

    def info(self) -> dict:
        return {"type": self.kind, "area_km2": round(self.area_km2, 1),
                "n_cells": int(len(self.cells)), "region_code": self.region_code}


def _geometry(aoi: AOI) -> BaseGeometry:
    if isinstance(aoi, BBoxAOI):
        w, s, e, n = aoi.bbox
        if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
            raise AOIError("bbox inválido: se espera [oeste, sur, este, norte] con oeste < este "
                           "y sur < norte, en grados WGS84.")
        return box(w, s, e, n)
    if isinstance(aoi, PointAOI):
        return buffer_km(Point(aoi.lon, aoi.lat), aoi.radius_km)
    if isinstance(aoi, GeoJSONAOI):
        gtype = aoi.geometry.get("type")
        if gtype not in ("Polygon", "MultiPolygon"):
            raise AOIError(f"La geometría GeoJSON debe ser Polygon o MultiPolygon (llegó {gtype}).")
        try:
            geom = shape(aoi.geometry)
        except Exception as exc:  # noqa: BLE001 - cualquier error de parseo es un 422
            raise AOIError(f"Geometría GeoJSON no válida: {exc}") from exc
        if geom.is_empty or not geom.is_valid:
            raise AOIError(f"Geometría GeoJSON no válida: {explain_validity(geom)}")
        w, s, e, n = geom.bounds
        if w < -180 or e > 180 or s < -90 or n > 90:
            raise AOIError("Coordenadas fuera de rango: se espera WGS84 (lon, lat) en grados.")
        return geom
    raise AOIError("Tipo de AOI no soportado.")


def resolve_aoi(aoi: AOI, repo: Repository, *, region_exempt: bool) -> ResolvedAOI:
    """Valida el AOI y obtiene sus celdas H3. ``region_exempt``: ignora max_aoi_km2 si es región."""
    api = repo.settings.params.api
    if isinstance(aoi, RegionAOI):
        region = repo.regions.get(aoi.code)
        if region is None:
            raise AOIError(f"Región desconocida '{aoi.code}'. Disponibles: {sorted(repo.regions)}")
        if not region_exempt and region.area_km2 > api.max_aoi_km2:
            raise AOIError(f"La región mide {region.area_km2:,.0f} km², más que el máximo "
                           f"permitido ({api.max_aoi_km2:,.0f} km²) para esta consulta.")
        return ResolvedAOI("region", region.geometry, region.area_km2,
                           repo.region_cells[aoi.code], aoi.code)
    if isinstance(aoi, PointAOI) and aoi.radius_km > api.max_point_radius_km:
        raise AOIError(f"radius_km debe ser <= {api.max_point_radius_km} km.")
    geom = _geometry(aoi)
    area = geodesic_area_km2(geom)
    if area > api.max_aoi_km2:
        raise AOIError(f"El AOI mide {area:,.0f} km², más que el máximo permitido "
                       f"({api.max_aoi_km2:,.0f} km²).")
    res = repo.settings.params.grid.h3_res_store
    cells = polygon_cells(geom, res)
    if not cells:  # AOI más chico que una celda: la celda que contiene su centro
        c = geom.centroid
        cells = set(latlng_to_cells(np.array([c.y]), np.array([c.x]), res))
    return ResolvedAOI(aoi.type, geom, area, np.array(sorted(cells), dtype=object))


def envelope(repo: Repository, notes: list[str]) -> dict:
    """Campos comunes: data_mode, data_version, generated_at y notes (sin duplicados)."""
    base = [NOTE_SYNTHETIC] if repo.data_mode == "synthetic" else []
    if repo.data_mode != repo.settings.data_mode:
        base.append(f"Atención: los datos se generaron en modo '{repo.data_mode}' pero "
                    f"FIRECAL_DATA_MODE es '{repo.settings.data_mode}'. Vuelve a correr el "
                    "pipeline.")
    seen, out = set(), []
    for n in [*base, *notes]:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return {"data_mode": repo.data_mode, "data_version": repo.data_version,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "notes": out}


def outside_note(repo: Repository, aoi: ResolvedAOI) -> list[str]:
    known = set(repo.known_cells())
    return [] if any(c in known for c in aoi.cells) else [NOTE_OUTSIDE]


def clean_number(x, digits: int = 3):
    """float redondeado o None (NaN -> None) para JSON."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(f) else round(f, digits)
