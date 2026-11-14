"""Descarga de datos NRT recientes con la API ``area`` de FIRMS. **PENDIENTE (Fase R).**

Lo que hará cuando se implemente:

- Consultar ``/api/area/csv/{MAP_KEY}/{SOURCE}/{w,s,e,n}/{DAY_RANGE}/{YYYY-MM-DD}`` para
  ``MODIS_NRT``, ``VIIRS_NOAA20_NRT`` y ``VIIRS_NOAA21_NRT`` (no ``VIIRS_SNPP_NRT``: S-NPP dejó
  de producir datos el 2026-11-02), sobre el bbox de la región + buffer.
- Verificar en la documentación de FIRMS el máximo de días por solicitud y trocear el rango.
- Respetar el límite de transacciones de la MAP_KEY y reintentar con *backoff* exponencial
  (``httpx``).
- Guardar cada respuesta cruda en ``data/raw/firms/nrt/`` para que ``archive_loader`` la lea.
- Error claro si no hay ``FIRMS_MAP_KEY``. La clave nunca aparece en logs
  (``firecal.logging_utils.redact``).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from firecal.settings import Settings

NRT_SOURCES = ("MODIS_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT")

PENDING_MESSAGE = (
    "La descarga NRT desde la API de FIRMS esta pendiente (Fase R: datos reales). "
    "Por ahora el backend trabaja solo en modo sintetico."
)


def fetch_nrt(
    settings: Settings,
    *,
    sources: tuple[str, ...] = NRT_SOURCES,
    day_range: int | None = None,
    end: date | None = None,
) -> list[Path]:
    """Descarga los últimos ``day_range`` días hasta ``end`` y devuelve los CSV guardados.

    TODO-REAL: verificar en la documentación de FIRMS el máximo de días por solicitud.
    """
    raise NotImplementedError(PENDING_MESSAGE)
