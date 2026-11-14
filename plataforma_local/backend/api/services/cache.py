"""Caché de respuestas precalculadas por región (``firecal precompute``).

Solo para las consultas por defecto (región completa, modo armonizado, años por defecto; anomalía
del último mes). La caché se invalida sola si cambia la base de datos (``Repository.cache_key``).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from api.db import Repository

log = logging.getLogger(__name__)


def _path(repo: Repository, kind: str, code: str) -> Path:
    return repo.settings.paths.cache_dir / f"{kind}_{code}.json"


def read(repo: Repository, kind: str, code: str) -> dict | None:
    path = _path(repo, kind, code)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.pop("_cache_key", None) != repo.cache_key:
        return None
    return data


def write(repo: Repository, kind: str, code: str, payload: dict) -> Path:
    path = _path(repo, kind, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**payload, "_cache_key": repo.cache_key}, ensure_ascii=False),
                    encoding="utf-8", newline="\n")
    return path


def precompute(repo: Repository) -> list[Path]:
    """Calendario y anomalía por defecto de cada región."""
    from api.schemas import RegionAOI
    from api.services.common import resolve_aoi
    from api.services.series import anomaly_report, calendar

    repo.ensure_loaded()
    written = []
    for code in sorted(repo.regions):
        aoi = resolve_aoi(RegionAOI(type="region", code=code), repo, region_exempt=True)
        written.append(write(repo, "calendar", code, calendar(repo, aoi, "harmonized", None,
                                                              None)))
        written.append(write(repo, "anomaly", code, anomaly_report(repo, aoi, None, None)))
        log.info("Precalculado: %s", code)
    return written
