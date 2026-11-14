"""Esquemas Pydantic de entrada y salida de la API."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from firecal.settings import DataMode

# --------------------------------------------------------------------------------------
# AOI (área de interés): un solo esquema con discriminador `type`
# --------------------------------------------------------------------------------------


class RegionAOI(BaseModel):
    type: Literal["region"]
    code: str = Field(description="Código de región (ver GET /api/v1/regions).")


class BBoxAOI(BaseModel):
    type: Literal["bbox"]
    bbox: list[float] = Field(min_length=4, max_length=4,
                              description="[oeste, sur, este, norte] en grados WGS84.")


class PointAOI(BaseModel):
    type: Literal["point"]
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    radius_km: float = Field(gt=0, description="Radio del círculo alrededor del punto (km).")


class GeoJSONAOI(BaseModel):
    type: Literal["geojson"]
    geometry: dict[str, Any] = Field(description="GeoJSON Polygon o MultiPolygon (WGS84).")


AOI = Annotated[RegionAOI | BBoxAOI | PointAOI | GeoJSONAOI, Field(discriminator="type")]

_AOI_EXAMPLE = {"type": "region", "code": "peru_sur"}
_BBOX_EXAMPLE = {"type": "bbox", "bbox": [-72.6, -13.8, -71.8, -13.2]}

CalendarMode = Literal["harmonized", "percentile", "raw_modis", "raw_viirs"]
Reliability = Literal["alta", "media", "baja"]

# --------------------------------------------------------------------------------------
# Solicitudes
# --------------------------------------------------------------------------------------


class CalendarRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"aoi": _AOI_EXAMPLE, "mode": "harmonized"},
        {"aoi": _BBOX_EXAMPLE, "mode": "percentile", "start_year": 2015, "end_year": 2026},
    ]})
    aoi: AOI
    mode: CalendarMode = "harmonized"
    start_year: int | None = Field(default=None, description="Por defecto: series_start.")
    end_year: int | None = Field(default=None, description="Por defecto: último año con datos.")


class AnomalyRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"aoi": _AOI_EXAMPLE},
        {"aoi": {"type": "point", "lat": -13.5, "lon": -72.0, "radius_km": 25},
         "year": 2025, "month": 9},
    ]})
    aoi: AOI
    year: int | None = Field(default=None, description="Por defecto: último mes con datos.")
    month: int | None = Field(default=None, ge=1, le=12)


class HotspotsRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"aoi": _BBOX_EXAMPLE, "start": "2025-08-01", "end": "2025-09-30", "format": "csv"},
    ]})
    aoi: AOI
    start: date = Field(description="Fecha local (America/Lima) inicial, inclusive.")
    end: date = Field(description="Fecha local final, inclusive.")
    format: Literal["csv", "geojson"] = "csv"


class MapCellsRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"aoi": _AOI_EXAMPLE, "year": 2025, "month": 9},
    ]})
    aoi: AOI
    year: int
    month: int = Field(ge=1, le=12)


class ForecastRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"region_code": "peru_sur"}]})
    region_code: str


# --------------------------------------------------------------------------------------
# Respuestas
# --------------------------------------------------------------------------------------


class Envelope(BaseModel):
    """Campos presentes en toda respuesta JSON."""

    data_mode: DataMode
    data_version: str
    generated_at: str
    notes: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    data_mode: DataMode
    data_ready: bool


class AOIInfo(BaseModel):
    type: str
    area_km2: float
    n_cells: int
    region_code: str | None = None


class CalendarCell(BaseModel):
    year: int
    month: int
    value: float | None = Field(description="Valor según el modo (None si no se puede calcular).")
    band_p10: float | None = None
    band_p90: float | None = None
    percentile: float | None = None
    source: str
    satellite: str | None = None
    provisional: bool
    low_confidence: bool = False


class ClimatologyMonth(BaseModel):
    month: int
    median: float | None
    p25: float | None
    p75: float | None
    p90: float | None
    n_years: int


class CalendarResponse(Envelope):
    unit: str
    mode: CalendarMode
    years: list[int]
    months: list[int]
    cells: list[CalendarCell]
    climatology: list[ClimatologyMonth]
    aoi: AOIInfo
    reliability: Reliability
    expected_annual: float | None


class AnomalyResponse(Envelope):
    unit: str
    aoi: AOIInfo
    reliability: Reliability
    expected_annual: float | None
    year: int
    month: int
    value: float
    band_p10: float | None
    band_p90: float | None
    median: float | None
    p25: float | None
    p75: float | None
    p90: float | None
    n_years: int
    anomaly_abs: float | None
    anomaly_pct: float | None
    percentile: float | None
    percentile_sensor: float | None
    category: str | None
    source: str
    satellite: str | None
    provisional: bool
    low_confidence: bool


class ForecastResponse(Envelope):
    region_code: str
    available: bool
    target_year: int | None = None
    target_month: int | None = None
    prob_above_median: float | None = None
    expected_value: float | None = None
    skill: dict[str, Any] | None = None
    beats_climatology: bool | None = None
    model_version: str | None = None


class ErrorResponse(BaseModel):
    detail: str
