"""GET /api/v1/meta: versión de datos, parámetros, métricas de validación y modo."""

from __future__ import annotations

from fastapi import APIRouter

from api.deps import RepoDep
from api.services.other import meta

router = APIRouter(tags=["meta"])


@router.get("/meta", summary="Metadatos: unidad, banda, armonización, validación, límites")
def get_meta(repo: RepoDep) -> dict:
    return meta(repo)
