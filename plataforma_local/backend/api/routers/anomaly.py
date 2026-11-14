"""POST /api/v1/anomaly: un mes frente a su mediana histórica."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import RepoDep
from api.schemas import AnomalyRequest, AnomalyResponse, ErrorResponse, RegionAOI
from api.services import cache
from api.services.common import resolve_aoi
from api.services.series import anomaly_report

router = APIRouter(tags=["anomalia"])


@router.post("/anomaly", response_model=AnomalyResponse,
             responses={422: {"model": ErrorResponse}},
             summary="Anomalía de un mes frente a la climatología")
def post_anomaly(req: AnomalyRequest, repo: RepoDep) -> dict:
    """Por defecto, el último mes con datos (puede ser provisional)."""
    default = isinstance(req.aoi, RegionAOI) and req.year is None and req.month is None
    if default and (cached := cache.read(repo, "anomaly", req.aoi.code)):
        return cached
    aoi = resolve_aoi(req.aoi, repo, region_exempt=True)
    return anomaly_report(repo, aoi, req.year, req.month)
