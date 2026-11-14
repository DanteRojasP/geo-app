"""POST /api/v1/forecast: perspectiva del mes siguiente para una región."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import RepoDep
from api.schemas import ErrorResponse, ForecastRequest, ForecastResponse
from api.services.other import forecast

router = APIRouter(tags=["perspectiva"])


@router.post("/forecast", response_model=ForecastResponse,
             responses={422: {"model": ErrorResponse}},
             summary="Perspectiva del mes siguiente (available=false hasta la Fase 7)")
def post_forecast(req: ForecastRequest, repo: RepoDep) -> dict:
    return forecast(repo, req.region_code)
