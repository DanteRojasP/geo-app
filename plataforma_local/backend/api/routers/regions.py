"""GET /api/v1/regions: regiones con geometría simplificada (GeoJSON)."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import RepoDep
from api.services.other import regions_geojson

router = APIRouter(tags=["regiones"])


@router.get("/regions", summary="Regiones disponibles (GeoJSON simplificado)")
def list_regions(repo: RepoDep) -> dict:
    return regions_geojson(repo)
