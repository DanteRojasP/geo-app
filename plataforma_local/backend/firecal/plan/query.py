"""Consultas sobre los datos armonizados de Cusco (Parquet + DuckDB).

Unidad (MAESTRO §1.2 y §12): **focos armonizados** = celdas de ~1 km con fuego por día, en escala
equivalente a MODIS. El valor de un periodo es la suma de ``eq_hotspots`` (celda-día) o de
``eq_foco`` (focos): nunca se cuentan filas ni se suma ``n_modis + n_viirs``. El FRP no se usa.

AOI:
- ``departamento=PE-CUS``: todo Cusco; el calendario suma ``eq_hotspots`` del CSV de celda-día.
- ``bbox`` o ``lat/lon/radio_km`` (dibujados): se filtran los focos por ``latitude/longitude`` y se
  suma ``eq_foco``. Así el total en pantalla es igual a la suma de la descarga CSV (P3).
- Otro departamento, o un área fuera de Cusco: **sin datos** (404), nunca ceros (MAESTRO §1.6).

Anomalía (alternativa C del PLAN): ``(valor - mediana del mismo mes) / max(IQR, 1)`` con los meses
completos de calidad ``referencia`` o ``calibrado`` (2002-08 a 2025-12) como historia.
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd
from shapely.geometry import Point, box, shape

from firecal.concurrency import SingleFlight
from firecal.plan.events import meta_path, plan_dir, region_path
from firecal.plan.sources import COLS_FOCOS, REGION_CODE, REGION_NAME
from firecal.regions import buffer_km, geodesic_area_km2
from firecal.settings import Settings

MIN_YEARS = 5
COVER_FROM = (2000, 11)            # primer mes con datos (desde el 2000-11-04)
COVER_TO = (2025, 12)              # último mes (datos hasta 2025-12-31 UTC)
AQUA_MONTH = (2002, 7)             # mes de transición Terra*kT -> MODIS (2002-07-04)
VIIRS_FROM = (2013, 1)             # desde aquí la serie usa VIIRS*k
CATEGORY_EDGES = [(-1.0, "muy por debajo"), (-0.5, "por debajo"), (0.5, "normal"),
                  (1.0, "por encima"), (math.inf, "muy por encima")]
EARTH_KM = 6371.0088
UNIDAD = ("Focos armonizados: celdas de ~1 km con fuego por día, en escala equivalente a MODIS. "
          "Combina MODIS (2000–2012) y VIIRS (2013 en adelante).")
NOTE_2025 = ("2025: el valor es el que registra VIIRS. MODIS cae más que VIIRS ese año (posible "
             "deriva orbital, no verificada), pero no afecta a la serie, que usa VIIRS desde 2013. "
             "El último día (31-dic) puede estar incompleto.")
NOTE_EXTRAPOLADO = ("2000-11 a 2002-07: solo Terra, escalado con kT (calidad 'extrapolado', error "
                    "mensual ~41–45 %). Se muestra atenuado.")
NOTE_CUSTOM = ("Área dibujada: el total es la suma de eq_foco de los focos dentro del área "
               "(igual a la suma de la descarga CSV).")


class PlanError(ValueError):
    """Error de la consulta con mensaje claro para el usuario (se responde 422)."""


class PlanNoData(LookupError):
    """La consulta es válida pero no hay datos (se responde 404 'sin datos')."""


class PlanNotReady(RuntimeError):
    """Todavía no se cargaron los datos (se responde 503)."""


@dataclass(frozen=True)
class AOI:
    kind: str                      # departamento | bbox | punto
    sql: str                       # condición WHERE sobre la tabla de focos (latitude/longitude)
    params: tuple
    label: str
    area_km2: float | None = None

    @property
    def whole_region(self) -> bool:
        return self.kind == "departamento"

    def info(self) -> dict:
        return {"tipo": self.kind, "descripcion": self.label,
                "area_km2": None if self.area_km2 is None else round(self.area_km2, 1)}


def parse_month(value: str | None, name: str) -> tuple[int, int] | None:
    if value in (None, ""):
        return None
    try:
        y, m = (int(v) for v in value.split("-")[:2])
        if not 1 <= m <= 12:
            raise ValueError
    except ValueError as exc:
        raise PlanError(f"{name} inválida ('{value}'): usa el formato AAAA-MM, "
                        "p. ej. 2020-08.") from exc
    return y, m


def month_quality(y: int, m: int) -> tuple[str, str]:
    """(calidad, fuente_serie) del mes según las reglas del contrato."""
    if (y, m) < AQUA_MONTH:
        return "extrapolado", "Terra*kT"
    if (y, m) == AQUA_MONTH:
        return "mixto", "Terra*kT + MODIS"
    if (y, m) < VIIRS_FROM:
        return "referencia", "MODIS"
    return "calibrado", "VIIRS*k"


def category(anom: float | None) -> str | None:
    if anom is None:
        return None
    for edge, name in CATEGORY_EDGES:
        if anom < edge:
            return name
    return CATEGORY_EDGES[-1][1]


def _num(x, digits: int = 2):
    if x is None:
        return None
    f = float(x)
    return None if math.isnan(f) else round(f, digits)


def _month_range(a: tuple[int, int], b: tuple[int, int]) -> list[tuple[int, int]]:
    out, (y, m) = [], a
    while (y, m) <= b:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def color_breaks(values: list[float]) -> list[float]:
    """Cortes de la rampa (MAESTRO P2): cuantiles 50/75/90/99 de los meses con fuego."""
    v = np.array([x for x in values if x and x > 0], dtype=float)
    if v.size == 0:
        return []
    qs = np.quantile(v, [0.5, 0.75, 0.9, 0.99])
    out = []
    for q in qs:
        r = round(float(q)) if q >= 10 else round(float(q), 1)
        if not out or r > out[-1]:
            out.append(r)
    return out


class PlanStore:
    """Lectura del Parquet de Cusco: una conexión DuckDB en memoria y un cursor por consulta."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._stamp: float | None = None
        self._meta: dict = {}
        self._region_geojson: dict = {}
        self._region = None
        self._monthly_cache: dict[tuple, pd.DataFrame] = {}
        self._flight = SingleFlight()

    # ---------------------------------------------------------------- carga
    @property
    def ready(self) -> bool:
        return meta_path(self.settings).is_file()

    def _ensure(self) -> duckdb.DuckDBPyConnection:
        if not self.ready:
            raise PlanNotReady("Aún no se cargaron los datos de Cusco. Corre: firecal plan-events")
        stamp = meta_path(self.settings).stat().st_mtime
        with self._lock:
            if self._con is None or stamp != self._stamp:
                if self._con is not None:
                    self._con.close()
                con = duckdb.connect()
                base = plan_dir(self.settings)
                for name, sub in (("cd", "celda_dia"), ("fo", "focos")):
                    glob = (base / sub / "**" / "*.parquet").as_posix()
                    con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{glob}', "
                                "hive_partitioning = true)")
                self._con, self._stamp = con, stamp
                self._monthly_cache.clear()
                self._flight.clear()
                self._meta = json.loads(meta_path(self.settings).read_text(encoding="utf-8"))
                self._region_geojson = json.loads(
                    region_path(self.settings).read_text(encoding="utf-8"))
                self._region = shape(self._region_geojson["features"][0]["geometry"])
            return self._con

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self._ensure().cursor()

    @property
    def meta(self) -> dict:
        self._ensure()
        return self._meta

    @property
    def region_geojson(self) -> dict:
        self._ensure()
        return self._region_geojson

    # ---------------------------------------------------------------- AOI
    def resolve_aoi(self, departamento: str | None = None, bbox: str | None = None,
                    lat: float | None = None, lon: float | None = None,
                    radio_km: float | None = None) -> AOI:
        api = self.settings.params.api
        self._ensure()
        given = [departamento not in (None, ""), bbox not in (None, ""),
                 lat is not None or lon is not None]
        if sum(given) == 0:
            raise PlanError("AOI vacío: indica 'departamento' (PE-CUS), 'bbox' "
                            "(oeste,sur,este,norte) o 'lat', 'lon' y 'radio_km'.")
        if sum(given) > 1:
            raise PlanError("Indica un solo tipo de AOI: departamento, bbox o punto + radio.")
        if departamento:
            code = departamento.strip().upper()
            if code not in (REGION_CODE, "CUSCO", "CUZCO"):
                raise PlanNoData(f"Sin datos para '{departamento}': el prototipo solo tiene datos "
                                 f"armonizados y validados de {REGION_NAME} ({REGION_CODE}).")
            return AOI("departamento", "TRUE", (), REGION_NAME,
                       geodesic_area_km2(self._region))
        if bbox:
            try:
                w, s, e, n = (float(v) for v in bbox.split(","))
            except ValueError as exc:
                raise PlanError("bbox inválido: usa 'oeste,sur,este,norte' en grados, "
                                "p. ej. -72.5,-14,-71.5,-13.") from exc
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise PlanError("bbox inválido: se espera oeste < este y sur < norte (WGS84).")
            geom = box(w, s, e, n)
            area = geodesic_area_km2(geom)
            if area > api.max_aoi_km2:
                raise PlanError(f"Área demasiado grande: el bbox mide {area:,.0f} km² y el máximo "
                                f"es {api.max_aoi_km2:,.0f} km². Usa el departamento o un área "
                                "menor.")
            self._require_inside(geom)
            return AOI("bbox", "longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?",
                       (w, e, s, n), f"bbox [{w}, {s}, {e}, {n}]", area)
        if lat is None or lon is None or radio_km is None:
            raise PlanError("Para un punto indica 'lat', 'lon' y 'radio_km'.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise PlanError("lat/lon fuera de rango (WGS84).")
        if not 0 < radio_km <= api.max_point_radius_km:
            raise PlanError(f"radio_km debe estar entre 0 y {api.max_point_radius_km} km.")
        self._require_inside(buffer_km(Point(lon, lat), radio_km))
        dlat = radio_km / 111.0
        dlon = radio_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        sql = ("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ? AND "
               f"2 * {EARTH_KM} * asin(sqrt(pow(sin(radians(latitude - ?) / 2), 2) + "
               "cos(radians(?)) * cos(radians(latitude)) * "
               "pow(sin(radians(longitude - ?) / 2), 2))) <= ?")
        params = (lat - dlat, lat + dlat, lon - dlon, lon + dlon, lat, lat, lon, radio_km)
        return AOI("punto", sql, params, f"{radio_km} km alrededor de ({lat}, {lon})",
                   math.pi * radio_km ** 2)

    def _require_inside(self, geom) -> None:
        if not geom.intersects(self._region):
            raise PlanNoData(f"Sin datos: el área está fuera de {REGION_NAME}, la única región "
                             "con datos armonizados y validados.")

    # ---------------------------------------------------------------- series
    def monthly(self, aoi: AOI) -> pd.DataFrame:
        """Serie mensual 2000-11..2025-12 (ceros reales dentro de la cobertura) + anomalía.

        Se guarda en memoria por AOI; un candado por AOI (``SingleFlight``) evita calcular la
        misma serie varias veces a la vez.
        """
        key = (aoi.kind, aoi.sql, aoi.params)

        def compute() -> pd.DataFrame:
            df = self._monthly(aoi)
            if len(self._monthly_cache) > 256:
                self._monthly_cache.clear()
            self._monthly_cache[key] = df
            return df

        return self._flight.run(key, lambda: self._monthly_cache.get(key), compute)

    def _monthly(self, aoi: AOI) -> pd.DataFrame:
        cur = self.cursor()
        if aoi.whole_region:
            df = cur.execute(
                "SELECT anio, mes, sum(eq_hotspots) AS eq_hotspots, count(*) AS celdas_dia, "
                "sum(n_modis) AS focos_modis, sum(n_viirs) AS focos_viirs "
                "FROM cd GROUP BY 1, 2").df()
        else:
            df = cur.execute(
                "SELECT anio, mes, sum(eq_foco) AS eq_hotspots, "
                "count(DISTINCT CASE WHEN en_serie = 1 THEN fecha_local || '|' || cell_lat || '|' "
                "|| cell_lon END) AS celdas_dia, "
                "count(*) FILTER (WHERE sensor = 'MODIS') AS focos_modis, "
                "count(*) FILTER (WHERE sensor = 'VIIRS') AS focos_viirs "
                f"FROM fo WHERE {aoi.sql} GROUP BY 1, 2", list(aoi.params)).df()
        cur.close()
        months = _month_range(COVER_FROM, COVER_TO)
        full = pd.DataFrame(months, columns=["anio", "mes"])
        full = full.merge(df.astype({"anio": int, "mes": int}), on=["anio", "mes"], how="left")
        for c in ("eq_hotspots", "celdas_dia", "focos_modis", "focos_viirs"):
            full[c] = full[c].fillna(0)
        q = [month_quality(y, m) for y, m in months]
        full["calidad"] = [c for c, _ in q]
        full["fuente_serie"] = [f for _, f in q]
        full["parcial"] = [(y, m) == COVER_FROM for y, m in months]   # empieza el 2000-11-04

        base = full[full["calidad"].isin(["referencia", "calibrado"]) & ~full["parcial"]]
        stats = base.groupby("mes")["eq_hotspots"].agg(
            mediana_hist="median", p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75), n_anios="size").reset_index()
        full = full.merge(stats, on="mes", how="left")
        iqr = np.maximum(full["p75"] - full["p25"], 1.0)
        anom = (full["eq_hotspots"] - full["mediana_hist"]) / iqr
        full["anomalia"] = anom.where((full["n_anios"] >= MIN_YEARS) & ~full["parcial"])
        return full

    def _range(self, inicio: str | None, fin: str | None) -> tuple[tuple, tuple]:
        a = parse_month(inicio, "fecha_inicio") or COVER_FROM
        b = parse_month(fin, "fecha_fin") or COVER_TO
        if a > b:
            raise PlanError(f"Rango invertido: fecha_inicio ({a[0]}-{a[1]:02d}) es posterior a "
                            f"fecha_fin ({b[0]}-{b[1]:02d}).")
        if b < COVER_FROM or a > COVER_TO:
            raise PlanNoData(f"Sin datos: la serie cubre de {COVER_FROM[0]}-{COVER_FROM[1]:02d} "
                             f"(desde el 2000-11-04) a {COVER_TO[0]}-{COVER_TO[1]:02d}.")
        return a, b

    def calendar(self, aoi: AOI, inicio: str | None, fin: str | None) -> dict:
        a, b = self._range(inicio, fin)
        full = self.monthly(aoi)
        if full["focos_modis"].sum() + full["focos_viirs"].sum() == 0:
            raise PlanNoData(f"Sin datos: no hay focos en {aoi.label} en toda la serie.")
        by_key = {(int(r.anio), int(r.mes)): r for r in full.itertuples(index=False)}
        months = _month_range(a, b)
        years = sorted({y for y, _ in months})
        mat_v = [[None] * 12 for _ in years]
        mat_a = [[None] * 12 for _ in years]
        cells, values, total = [], [], 0.0
        for y, m in months:
            i, j = years.index(y), m - 1
            r = by_key.get((y, m))
            if r is None:                       # fuera de la cobertura: sin dato, no cero
                cells.append({"anio": y, "mes": m, "sin_dato": True})
                continue
            v, anom = _num(r.eq_hotspots, 2), _num(r.anomalia)
            mat_v[i][j], mat_a[i][j] = v, anom
            values.append(v)
            total += float(r.eq_hotspots)
            cells.append({"anio": y, "mes": m, "sin_dato": False, "eq_hotspots": v,
                          "celdas_dia": int(r.celdas_dia), "focos_modis": int(r.focos_modis),
                          "focos_viirs": int(r.focos_viirs), "mediana_hist": _num(r.mediana_hist),
                          "anomalia": anom, "categoria": category(anom), "calidad": r.calidad,
                          "fuente_serie": r.fuente_serie, "parcial": bool(r.parcial)})
        notes = []
        if any(c.get("calidad") in ("extrapolado", "mixto") for c in cells):
            notes.append(NOTE_EXTRAPOLADO)
        if any(c["anio"] == 2025 and not c["sin_dato"] for c in cells):
            notes.append(NOTE_2025)
        if any(c["sin_dato"] for c in cells):
            notes.append("Meses sin dato (fuera de 2000-11-04 a 2025-12-31) en gris: no son cero.")
        if not aoi.whole_region:
            notes.append(NOTE_CUSTOM)
        return {"aoi": aoi.info(), "unidad": UNIDAD, "fecha_inicio": f"{a[0]}-{a[1]:02d}",
                "fecha_fin": f"{b[0]}-{b[1]:02d}", "anios": years, "meses": list(range(1, 13)),
                "matriz_eq_hotspots": mat_v, "matriz_anomalia": mat_a,
                "total_eq_hotspots": round(total, 2), "cortes_color": color_breaks(values),
                "celdas": cells, "notes": notes}

    def anomaly(self, aoi: AOI, mes: str) -> dict:
        ym = parse_month(mes, "mes")
        if ym is None:
            raise PlanError("Indica 'mes' con el formato AAAA-MM.")
        if not COVER_FROM <= ym <= COVER_TO:
            raise PlanNoData(f"Sin datos para {mes}: la serie cubre de 2000-11 a 2025-12.")
        full = self.monthly(aoi)
        r = full[(full["anio"] == ym[0]) & (full["mes"] == ym[1])].iloc[0]
        hist = full[(full["mes"] == ym[1]) & full["calidad"].isin(["referencia", "calibrado"])
                    & ~full["parcial"]]
        cur = self.cursor()
        if aoi.whole_region:
            days = cur.execute("SELECT fecha_local, sum(eq_hotspots) FROM cd WHERE anio = ? AND "
                               "mes = ? GROUP BY 1 ORDER BY 1", [ym[0], ym[1]]).fetchall()
        else:
            days = cur.execute(f"SELECT fecha_local, sum(eq_foco) FROM fo WHERE {aoi.sql} AND "
                               "anio = ? AND mes = ? AND en_serie = 1 GROUP BY 1 ORDER BY 1",
                               [*aoi.params, ym[0], ym[1]]).fetchall()
        cur.close()
        anom = _num(r["anomalia"])
        notes = []
        if r["calidad"] in ("extrapolado", "mixto"):
            notes.append(NOTE_EXTRAPOLADO)
        if ym[0] == 2025:
            notes.append(NOTE_2025)
        if anom is None and not bool(r["parcial"]):
            notes.append(f"Sin anomalía: hay menos de {MIN_YEARS} años de historia.")
        if bool(r["parcial"]):
            notes.append("Mes parcial (la serie empieza el 2000-11-04): sin anomalía.")
        return {"aoi": aoi.info(), "unidad": UNIDAD, "mes": f"{ym[0]}-{ym[1]:02d}",
                "eq_hotspots": _num(r["eq_hotspots"]), "celdas_dia": int(r["celdas_dia"]),
                "focos_modis": int(r["focos_modis"]), "focos_viirs": int(r["focos_viirs"]),
                "calidad": r["calidad"], "fuente_serie": r["fuente_serie"],
                "mediana_hist": _num(r["mediana_hist"]), "p25": _num(r["p25"]),
                "p75": _num(r["p75"]), "n_anios_hist": int(r["n_anios"] or 0),
                "anomalia": anom, "categoria": category(anom), "parcial": bool(r["parcial"]),
                "historial": [{"anio": int(x.anio), "eq_hotspots": _num(x.eq_hotspots)}
                              for x in hist.itertuples(index=False)],
                "dias": [{"fecha_local": d, "eq_hotspots": _num(v, 3)} for d, v in days],
                "notes": notes}

    # ---------------------------------------------------------------- CSV
    def hotspots_query(self, aoi: AOI, inicio: str | None, fin: str | None
                       ) -> tuple[str, list, int, float]:
        """SQL de la descarga (18 columnas del contrato de focos), n.º de filas y Σ eq_foco."""
        if inicio in (None, "") or fin in (None, ""):
            raise PlanError("Para la descarga indica 'fecha_inicio' y 'fecha_fin' (AAAA-MM).")
        a, b = self._range(inicio, fin)
        where = f"WHERE {aoi.sql} AND (anio * 100 + mes) BETWEEN ? AND ?"
        params = [*aoi.params, a[0] * 100 + a[1], b[0] * 100 + b[1]]
        cur = self.cursor()
        n, total = cur.execute(f"SELECT count(*), coalesce(sum(eq_foco), 0) FROM fo {where}",
                               params).fetchall()[0]
        cur.close()
        max_rows = self.settings.params.api.max_csv_rows
        if n > max_rows:
            raise PlanError(f"La descarga tendría {n:,} filas; el máximo es {max_rows:,}. "
                            "Usa un rango de fechas o un área menor.")
        sql = (f"SELECT {', '.join(COLS_FOCOS)} FROM fo {where} "
               "ORDER BY fecha_utc, hora_utc, latitude, longitude")
        return sql, params, int(n), float(total)
