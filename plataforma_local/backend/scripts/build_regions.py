"""Genera config/regions/peru_departamentos.geojson a partir de geoBoundaries (ADM1 Perú).

Uso (desde backend/):
    .venv/Scripts/python scripts/build_regions.py               # departamentos por defecto
    .venv/Scripts/python scripts/build_regions.py PE-CUS PE-PUN # otra selección (códigos ISO)

Escribe:
- un Feature por departamento (code = ISO 3166-2, p. ej. "PE-CUS"; level = "departamento");
- un Feature "peru_sur" = unión de los departamentos (región de trabajo del pipeline,
  FIRECAL_REGION), level = "conjunto".
Imprime el bbox de la unión para copiarlo en config/settings.yaml -> region.bbox.

Fuente: geoBoundaries gbOpen PER ADM1 (simplificado), licencia abierta (CC BY 4.0).
Runfola et al. (2020) geoBoundaries. PLoS ONE 15(4): e0231866.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "config" / "regions_src" / "geoBoundaries-PER-ADM1_simplified.geojson"
OUT = ROOT / "config" / "regions" / "peru_departamentos.geojson"

# Selección por defecto (decisión pendiente del equipo, PLAN.md sección 9): departamentos
# del sur andino-amazónico con mucha actividad de quema histórica.
DEFAULT = ["PE-CUS", "PE-APU", "PE-AYA", "PE-PUN", "PE-MDD"]
UNION_CODE = "peru_sur"


def main(codes: list[str]) -> None:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    by_iso = {f["properties"]["shapeISO"]: f for f in data["features"]}
    missing = [c for c in codes if c not in by_iso]
    if missing:
        raise SystemExit(f"Codigos no encontrados: {missing}. Disponibles: {sorted(by_iso)}")

    feats, geoms = [], []
    for code in codes:
        f = by_iso[code]
        geom = shape(f["geometry"]).buffer(0)  # repara anillos inválidos de la simplificación
        geoms.append(geom)
        feats.append({"type": "Feature",
                      "properties": {"code": code, "name": f["properties"]["shapeName"],
                                     "level": "departamento"},
                      "geometry": mapping(geom)})
    union = unary_union(geoms).buffer(0)
    names = ", ".join(f["properties"]["name"] for f in feats)
    feats.insert(0, {"type": "Feature",
                     "properties": {"code": UNION_CODE, "name": f"Sur del Perú ({names})",
                                    "level": "conjunto"},
                     "geometry": mapping(union)})
    OUT.write_text(json.dumps({"type": "FeatureCollection", "features": feats},
                              ensure_ascii=False), encoding="utf-8")
    w, s, e, n = (round(v, 2) for v in union.bounds)
    print(f"OK {OUT.name}: {len(codes)} departamentos + '{UNION_CODE}'")
    print(f"region.bbox para settings.yaml: [{w}, {s}, {e}, {n}]")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
