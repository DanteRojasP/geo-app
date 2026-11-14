"""Esquema de los CSV de FIRMS y **supuestos sobre el formato real** (TODO-REAL).

Todo lo que el pipeline asume sobre los archivos reales de FIRMS y que todavía NO se ha
verificado con datos reales está en ``FIRMS_ASSUMPTIONS``. Cuando lleguen CSV reales:
revisar cada entrada marcada TODO-REAL, corregirla aquí y correr los tests.
(La lista también está en CLAUDE.md, sección "Fase R".)
"""

from __future__ import annotations

from typing import Literal

Sensor = Literal["MODIS", "VIIRS"]

# Columnas que identifican cada esquema (detección por columnas, no por nombre de archivo).
SCHEMA_SIGNATURE: dict[Sensor, set[str]] = {
    "MODIS": {"brightness", "bright_t31"},
    "VIIRS": {"bright_ti4", "bright_ti5"},
}
# Columnas mínimas que el loader necesita en ambos esquemas. `type` es opcional (solo en SP).
REQUIRED_COLUMNS = {
    "latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "version",
    "frp", "daynight",
}

FIRMS_ASSUMPTIONS: dict = {
    # (sensor, valor de la columna `satellite`) -> satélite normalizado.
    # Los códigos de los CSV sintéticos están verificados (los escribe nuestro simulador).
    # TODO-REAL: verificar qué códigos usan los CSV reales (archivo SP y NRT) de cada producto.
    # Un código que no esté aquí se registra en el log y sus filas se descartan (no se adivina).
    "satellite_codes": {
        ("MODIS", "Terra"): "TERRA",
        ("MODIS", "Aqua"): "AQUA",
        ("VIIRS", "N"): "SNPP",
        ("VIIRS", "N20"): "N20",
        ("VIIRS", "N21"): "N21",
    },
    # TODO-REAL: acq_time es HHMM en UTC; se acepta con o sin ceros a la izquierda ("552" = 05:52).
    "acq_time_is_utc": True,
    # Clasificación de la columna `version` -> SP | NRT | SYN | SYN-NRT.
    # TODO-REAL: verificar los valores reales (se asume que las versiones NRT contienen "NRT",
    # p. ej. "6.1NRT", y que cualquier otra versión es SP/definitiva).
    "version_nrt_marker": "NRT",
    "version_synthetic_prefix": "SYN",
    # Confianza VIIRS -> categoría. TODO-REAL: verificar si el NRT usa palabras completas.
    "viirs_confidence": {
        "l": "low", "n": "nominal", "h": "high",
        "low": "low", "nominal": "nominal", "high": "high",
    },
    # TODO-REAL: valores de `daynight` ("D"/"N").
    "daynight_values": {"D", "N"},
    # TODO-REAL: `type` (0 vegetación, 1 volcán, 2 otra fuente fija, 3 mar adentro) solo en SP.
    "type_vegetation": 0,
}


def classify_version(raw: str) -> str:
    """Normaliza la columna ``version`` a SP | NRT | SYN | SYN-NRT."""
    v = str(raw).strip().upper()
    synthetic = v.startswith(FIRMS_ASSUMPTIONS["version_synthetic_prefix"])
    nrt = FIRMS_ASSUMPTIONS["version_nrt_marker"] in v
    if synthetic:
        return "SYN-NRT" if nrt else "SYN"
    return "NRT" if nrt else "SP"


def is_nrt_version(version: str) -> bool:
    """True para versiones provisionales (NRT o SYN-NRT)."""
    return version.endswith("NRT")
