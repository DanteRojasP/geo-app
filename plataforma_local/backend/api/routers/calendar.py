"""POST /api/v1/calendar: matriz año x mes de un AOI."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import RepoDep
from api.schemas import CalendarRequest, CalendarResponse, ErrorResponse, RegionAOI
from api.services import cache
from api.services.common import resolve_aoi
from api.services.series import calendar

router = APIRouter(tags=["calendario"])


@router.post("/calendar", response_model=CalendarResponse,
             responses={422: {"model": ErrorResponse}},
             summary="Calendario de actividad de quema (año x mes)")
def post_calendar(req: CalendarRequest, repo: RepoDep) -> dict:
    """Matriz año x mes para el heatmap. `mode`: harmonized (por defecto), percentile,
    raw_modis o raw_viirs. Las AOI de tipo `region` no tienen límite de área."""
    default = (isinstance(req.aoi, RegionAOI) and req.mode == "harmonized"
               and req.start_year is None and req.end_year is None)
    if default and (cached := cache.read(repo, "calendar", req.aoi.code)):
        return cached
    aoi = resolve_aoi(req.aoi, repo, region_exempt=True)
    return calendar(repo, aoi, req.mode, req.start_year, req.end_year)
