"""POST /api/v1/hotspots: focos dentro de un AOI (CSV en streaming o GeoJSON)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.deps import RepoDep
from api.schemas import ErrorResponse, HotspotsRequest
from api.services.common import AOIError, resolve_aoi
from api.services.other import csv_stream, hotspots_geojson, hotspots_in_aoi

router = APIRouter(tags=["focos"])


@router.post("/hotspots", responses={422: {"model": ErrorResponse},
                                     200: {"content": {"text/csv": {}}}},
             summary="Descarga de focos limpios dentro del AOI")
def post_hotspots(req: HotspotsRequest, repo: RepoDep, request: Request):
    """Filtro exacto punto-en-polígono. Rango máximo `max_csv_years` (también para regiones).
    CSV en utf-8 con BOM (abre bien en Excel); incluye la columna `data_mode`."""
    aoi = resolve_aoi(req.aoi, repo, region_exempt=False)
    with request.app.state.gate.turn():  # consulta pesada: turno en HeavyGate
        df = hotspots_in_aoi(repo, aoi, req.start, req.end)
    max_rows = repo.settings.params.api.max_csv_rows
    if len(df) > max_rows:
        raise AOIError(f"La descarga tendría {len(df):,} focos; el máximo es {max_rows:,}. Usa un "
                       "rango de fechas o un área menor.")
    if req.format == "geojson":
        return hotspots_geojson(repo, df, aoi)
    name = f"firecal_focos_{repo.data_mode}_{req.start}_{req.end}.csv"
    return StreamingResponse(
        csv_stream(df, repo.data_mode, repo.settings.params.api.csv_chunk_rows),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"',
                 "X-Data-Mode": repo.data_mode, "X-Row-Count": str(len(df))},
    )
