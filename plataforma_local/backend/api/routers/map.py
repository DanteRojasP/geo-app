"""POST /api/v1/map/cells: hexágonos H3 con valor armonizado de un mes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from api.deps import RepoDep
from api.schemas import ErrorResponse, MapCellsRequest
from api.services.common import resolve_aoi
from api.services.other import map_cells

router = APIRouter(tags=["mapa"])


@router.post("/map/cells", responses={422: {"model": ErrorResponse}},
             summary="Celdas H3 del AOI con valor armonizado (GeoJSON)")
def post_map_cells(req: MapCellsRequest, repo: RepoDep, request: Request) -> dict:
    aoi = resolve_aoi(req.aoi, repo, region_exempt=True)
    with request.app.state.gate.turn():  # consulta pesada: turno en HeavyGate
        return map_cells(repo, aoi, req.year, req.month)
