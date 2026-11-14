"""Consultas del plan (A + C) sobre el Parquet de eventos con DuckDB.

AOI admitidos (PLAN.md sección 4): departamento del Perú (principal), bbox o centro + radio.

Anomalía normalizada (alternativa C): cada mes se compara con la mediana histórica del MISMO mes
calendario dentro de la MISMA era de sensores (``MODIS`` antes de feb-2012; ``MODIS+VIIRS``
desde feb-2012). Así el aumento de detecciones que trae VIIRS no se lee como más fuego:

    anomalia = (n_eventos - mediana_era_mes) / max(IQR_era_mes, 1)

Con menos de ``MIN_YEARS`` años completos en la era no se calcula (aviso en ``notes``).
"""

from __future__ import annotations

import json
import math
import threading
from dataclasses import dataclass
from datetime import date

import duckdb
import numpy as np
import pandas as pd

from firecal.concurrency import SingleFlight
from firecal.plan.events import VIIRS_ERA_START, events_dir, meta_path
from firecal.regions import geodesic_area_km2, load_regions
from firecal.settings import Settings

MIN_YEARS = 5
# Categorías por anomalía normalizada (en unidades de IQR).
CATEGORY_EDGES = [(-1.0, "muy por debajo"), (-0.5, "por debajo"), (0.5, "normal"),
                  (1.0, "por encima"), (math.inf, "muy por encima")]
CSV_COLUMNS = ["fecha_utc", "hora", "lat", "lon", "celda_1km", "sensor", "satelite",
               "confianza_norm", "frp_mw", "dia_noche", "fecha_local", "n_detecciones",
               "sensores", "departamento"]
EARTH_KM = 6371.0088


class PlanError(ValueError):
    """Error de la consulta con mensaje claro para el usuario (se responde 422)."""


class PlanNoData(LookupError):
    """La consulta es válida pero no hay datos (se responde 404)."""


class PlanNotReady(RuntimeError):
    """Todavía no existe el Parquet de eventos (se responde 503)."""


@dataclass(frozen=True)
class AOI:
    kind: str                      # departamento | bbox | punto
    sql: str                       # condición WHERE con parámetros ?
    params: tuple
    label: str
    area_km2: float | None = None

    def info(self) -> dict:
        return {"tipo": self.kind, "descripcion": self.label,
                "area_km2": None if self.area_km2 is None else round(self.area_km2, 1)}


def parse_month(value: str | None, name: str) -> tuple[int, int] | None:
    if value in (None, ""):
        return None
    try:
        y, m = value.split("-")[:2]
        y, m = int(y), int(m)
        if not 1 <= m <= 12:
            raise ValueError
    except ValueError as exc:
        raise PlanError(f"{name} inválida ('{value}'): usa el formato AAAA-MM, "
                        "p. ej. 2020-08.") from exc
    return y, m


def era_of(year: int, month: int) -> str:
    return "MODIS+VIIRS" if (year, month) >= VIIRS_ERA_START else "MODIS"


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


class PlanStore:
    """Lectura del Parquet de eventos: una conexión DuckDB en memoria y un cursor por consulta."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._con: duckdb.DuckDBPyConnection | None = None
        self._stamp: float | None = None
        self._meta: dict = {}
        self._departments: dict[str, dict] = {}
        self._monthly_cache: dict[tuple, pd.DataFrame] = {}
        self._flight = SingleFlight()

    # ---------------------------------------------------------------- carga
    @property
    def ready(self) -> bool:
        return meta_path(self.settings).is_file() and events_dir(self.settings).is_dir()

    def _ensure(self) -> duckdb.DuckDBPyConnection:
        if not self.ready:
            raise PlanNotReady("Aún no hay eventos armonizados. Corre: "
                               "firecal all --mode synthetic "
                               "(o firecal plan-events si el pipeline ya corrió).")
        stamp = meta_path(self.settings).stat().st_mtime
        with self._lock:
            if self._con is None or stamp != self._stamp:
                if self._con is not None:
                    self._con.close()
                con = duckdb.connect()
                glob = (events_dir(self.settings) / "**" / "*.parquet").as_posix()
                con.execute(f"CREATE VIEW ev AS SELECT * FROM read_parquet('{glob}', "
                            "hive_partitioning = true)")
                self._con, self._stamp = con, stamp
                self._monthly_cache.clear()
                self._flight.clear()
                self._meta = json.loads(meta_path(self.settings).read_text(encoding="utf-8"))
                self._departments = {
                    r.code: {"code": r.code, "name": r.name, "area_km2": r.area_km2}
                    for r in load_regions(self.settings.paths.regions_dir).values()
                    if r.level == "departamento"}
            return self._con

    def cursor(self) -> duckdb.DuckDBPyConnection:
        return self._ensure().cursor()

    @property
    def meta(self) -> dict:
        self._ensure()
        return self._meta

    @property
    def departments(self) -> dict[str, dict]:
        self._ensure()
        return self._departments

    # ---------------------------------------------------------------- AOI
    def resolve_aoi(self, departamento: str | None = None, bbox: str | None = None,
                    lat: float | None = None, lon: float | None = None,
                    radio_km: float | None = None) -> AOI:
        api = self.settings.params.api
        given = [departamento not in (None, ""), bbox not in (None, ""),
                 lat is not None or lon is not None]
        if sum(given) == 0:
            raise PlanError("AOI vacío: indica 'departamento' (p. ej. PE-CUS), 'bbox' "
                            "(oeste,sur,este,norte) o 'lat', 'lon' y 'radio_km'.")
        if sum(given) > 1:
            raise PlanError("Indica un solo tipo de AOI: departamento, bbox o punto + radio.")
        if departamento:
            code = departamento.upper()
            dep = self.departments.get(code)
            if dep is None:
                raise PlanError(f"Departamento desconocido '{departamento}'. Disponibles: "
                                f"{', '.join(sorted(self.departments))}.")
            return AOI("departamento", "departamento = ?", (code,), dep["name"], dep["area_km2"])
        if bbox:
            try:
                w, s, e, n = (float(v) for v in bbox.split(","))
            except ValueError as exc:
                raise PlanError("bbox inválido: usa 'oeste,sur,este,norte' en grados, "
                                "p. ej. -72.5,-14,-71.5,-13.") from exc
            if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
                raise PlanError("bbox inválido: se espera oeste < este y sur < norte (WGS84).")
            from shapely.geometry import box
            area = geodesic_area_km2(box(w, s, e, n))
            if area > api.max_aoi_km2:
                raise PlanError(f"Área demasiado grande: el bbox mide {area:,.0f} km² y el máximo "
                                f"es {api.max_aoi_km2:,.0f} km². Usa un departamento o un "
                                "área menor.")
            return AOI("bbox", "lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?", (w, e, s, n),
                       f"bbox [{w}, {s}, {e}, {n}]", area)
        if lat is None or lon is None or radio_km is None:
            raise PlanError("Para un punto indica 'lat', 'lon' y 'radio_km'.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise PlanError("lat/lon fuera de rango (WGS84).")
        if not 0 < radio_km <= api.max_point_radius_km:
            raise PlanError(f"radio_km debe estar entre 0 y {api.max_point_radius_km} km.")
        # Prefiltro por caja + distancia haversine exacta.
        dlat = radio_km / 111.0
        dlon = radio_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))
        sql = ("lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND "
               f"2 * {EARTH_KM} * asin(sqrt(pow(sin(radians(lat - ?) / 2), 2) + cos(radians(?)) "
               "* cos(radians(lat)) * pow(sin(radians(lon - ?) / 2), 2))) <= ?")
        params = (lat - dlat, lat + dlat, lon - dlon, lon + dlon, lat, lat, lon, radio_km)
        return AOI("punto", sql, params, f"{radio_km} km alrededor de ({lat}, {lon})",
                   math.pi * radio_km ** 2)

    # ---------------------------------------------------------------- series
    def _month_bounds(self) -> tuple[tuple[int, int], tuple[int, int], bool]:
        """(primer mes, último mes con datos, si el último está incompleto)."""
        y0, m0 = (int(v) for v in self.meta["primer_mes"].split("-"))
        last = date.fromisoformat(self.meta["ultimo_fecha_local"])
        nxt = date.fromordinal(last.toordinal() + 1)
        partial = nxt.month == last.month
        return (y0, m0), (last.year, last.month), partial

    def monthly(self, aoi: AOI) -> pd.DataFrame:
        """Serie mensual completa (con ceros) + mediana/IQR por era y anomalía normalizada.

        Se guarda en memoria por AOI (los departamentos se repiten mucho; ~5 KB por serie).
        Un candado por AOI (``SingleFlight``) evita calcular la misma serie varias veces a la vez.
        """
        key = (aoi.sql, aoi.params)

        def compute() -> pd.DataFrame:
            df = self._monthly(aoi)
            if len(self._monthly_cache) > 256:
                self._monthly_cache.clear()
            self._monthly_cache[key] = df
            return df

        # Solicitudes simultáneas del mismo AOI: una calcula y las demás reutilizan el resultado.
        return self._flight.run(key, lambda: self._monthly_cache.get(key), compute)

    def _monthly(self, aoi: AOI) -> pd.DataFrame:
        cur = self.cursor()
        df = cur.execute(f"SELECT anio, mes, count(*) AS n_eventos, sum(frp_mw) AS frp_total "
                         f"FROM ev WHERE {aoi.sql} GROUP BY 1, 2", list(aoi.params)).df()
        cur.close()
        (y0, m0), (y1, m1), partial = self._month_bounds()
        idx = pd.period_range(f"{y0}-{m0:02d}", f"{y1}-{m1:02d}", freq="M")
        full = pd.DataFrame({"anio": idx.year.astype(int), "mes": idx.month.astype(int)})
        full = full.merge(df.astype({"anio": int, "mes": int}), on=["anio", "mes"], how="left")
        full["n_eventos"] = full["n_eventos"].fillna(0).astype(int)
        full["frp_total"] = full["frp_total"].fillna(0.0)
        full["era"] = [era_of(y, m) for y, m in zip(full["anio"], full["mes"], strict=True)]
        full["parcial"] = False
        if partial:
            full.loc[full.index[-1], "parcial"] = True

        hist = full[~full["parcial"]]
        stats = hist.groupby(["era", "mes"])["n_eventos"].agg(
            mediana_hist="median", p25=lambda s: s.quantile(0.25),
            p75=lambda s: s.quantile(0.75), n_anios="size").reset_index()
        full = full.merge(stats, on=["era", "mes"], how="left")
        iqr = np.maximum(full["p75"] - full["p25"], 1.0)
        anom = (full["n_eventos"] - full["mediana_hist"]) / iqr
        # Un mes parcial (en curso) se vería falsamente "por debajo": sin anomalía.
        full["anomalia"] = anom.where((full["n_anios"] >= MIN_YEARS) & ~full["parcial"])
        return full

    def calendar(self, aoi: AOI, inicio: str | None, fin: str | None) -> dict:
        full = self.monthly(aoi)
        if full["n_eventos"].sum() == 0:
            raise PlanNoData(f"Sin datos: no hay eventos en {aoi.label} en todo el historial. "
                             "Revisa que el AOI esté dentro de los departamentos procesados.")
        a, b = parse_month(inicio, "fecha_inicio"), parse_month(fin, "fecha_fin")
        first = (int(full["anio"].iloc[0]), int(full["mes"].iloc[0]))
        last = (int(full["anio"].iloc[-1]), int(full["mes"].iloc[-1]))
        a, b = a or first, b or last
        if a > b:
            raise PlanError(f"Rango invertido: fecha_inicio ({a[0]}-{a[1]:02d}) es posterior a "
                            f"fecha_fin ({b[0]}-{b[1]:02d}).")
        key = full["anio"] * 100 + full["mes"]
        sel = full[(key >= a[0] * 100 + a[1]) & (key <= b[0] * 100 + b[1])]
        if sel.empty:
            raise PlanNoData("Sin datos en el rango pedido. Hay datos de "
                             f"{first[0]}-{first[1]:02d} "
                             f"a {last[0]}-{last[1]:02d}.")
        years = sorted(sel["anio"].unique().tolist())
        mat_n = [[None] * 12 for _ in years]
        mat_a = [[None] * 12 for _ in years]
        cells = []
        for r in sel.itertuples(index=False):
            i, j = years.index(r.anio), r.mes - 1
            anom = _num(r.anomalia)
            mat_n[i][j] = int(r.n_eventos)
            mat_a[i][j] = anom
            cells.append({"anio": int(r.anio), "mes": int(r.mes), "n_eventos": int(r.n_eventos),
                          "frp_total": _num(r.frp_total, 1),
                          "mediana_hist": _num(r.mediana_hist, 1),
                          "anomalia": anom, "categoria": category(anom), "era": r.era,
                          "parcial": bool(r.parcial)})
        notes = []
        if (sel["anomalia"].isna() & ~sel["parcial"]).any():
            notes.append(f"Algunos meses no tienen anomalía: su era de sensores tiene menos de "
                         f"{MIN_YEARS} años completos de historia.")
        if sel["parcial"].any():
            notes.append("El mes en curso está incompleto ('parcial'): se muestra el conteo, "
                         "pero no "
                         "su anomalía.")
        if len({c["era"] for c in cells}) > 1:
            notes.append("El rango cruza el cambio de sensores (feb-2012): compara colores con el "
                         "modo 'anomalia', no con 'n_eventos'.")
        return {"aoi": aoi.info(), "fecha_inicio": f"{a[0]}-{a[1]:02d}",
                "fecha_fin": f"{b[0]}-{b[1]:02d}", "anios": years, "meses": list(range(1, 13)),
                "matriz_n_eventos": mat_n, "matriz_anomalia": mat_a, "celdas": cells,
                "notes": notes}

    def anomaly(self, aoi: AOI, mes: str) -> dict:
        ym = parse_month(mes, "mes")
        if ym is None:
            raise PlanError("Indica 'mes' con el formato AAAA-MM.")
        full = self.monthly(aoi)
        row = full[(full["anio"] == ym[0]) & (full["mes"] == ym[1])]
        if row.empty:
            raise PlanNoData(f"Sin datos para {mes}: fuera del periodo disponible.")
        r = row.iloc[0]
        same = full[(full["mes"] == ym[1]) & (full["era"] == r["era"]) & ~full["parcial"]]
        anom = _num(r["anomalia"])
        notes = []
        if anom is None and not bool(r["parcial"]):
            notes.append(f"Sin anomalía: la era {r['era']} tiene menos de {MIN_YEARS} años "
                         "completos.")
        if bool(r["parcial"]):
            notes.append("Mes en curso (parcial): el conteo subirá con los próximos días; la "
                         "anomalía se calcula cuando el mes termine.")
        if int(full["n_eventos"].sum()) == 0:
            notes.append("El AOI no tiene eventos en todo el historial.")
        return {"aoi": aoi.info(), "mes": f"{ym[0]}-{ym[1]:02d}", "era": r["era"],
                "n_eventos": int(r["n_eventos"]), "frp_total": _num(r["frp_total"], 1),
                "mediana_hist": _num(r["mediana_hist"], 1), "p25": _num(r["p25"], 1),
                "p75": _num(r["p75"], 1), "n_anios_hist": int(r["n_anios"] or 0),
                "anomalia": anom, "categoria": category(anom), "parcial": bool(r["parcial"]),
                "historial": [{"anio": int(x.anio), "n_eventos": int(x.n_eventos)}
                              for x in same.itertuples(index=False)],
                "notes": notes}

    # ---------------------------------------------------------------- CSV
    def hotspots_query(self, aoi: AOI, inicio: str | None, fin: str | None) -> tuple[str, list]:
        a, b = parse_month(inicio, "fecha_inicio"), parse_month(fin, "fecha_fin")
        if a is None or b is None:
            raise PlanError("Para la descarga indica 'fecha_inicio' y 'fecha_fin' (AAAA-MM).")
        if a > b:
            raise PlanError("Rango invertido: fecha_inicio es posterior a fecha_fin.")
        n_months = (b[0] - a[0]) * 12 + (b[1] - a[1]) + 1
        max_years = self.settings.params.api.max_csv_years
        if n_months > max_years * 12:
            raise PlanError(f"Rango demasiado largo para la descarga: {n_months} meses; el "
                            f"máximo es {max_years} años.")
        where = f"WHERE {aoi.sql} AND (anio * 100 + mes) BETWEEN ? AND ?"
        params = [*aoi.params, a[0] * 100 + a[1], b[0] * 100 + b[1]]
        cur = self.cursor()
        n = cur.execute(f"SELECT count(*) FROM ev {where}", params).fetchall()[0][0]
        cur.close()
        max_rows = self.settings.params.api.max_csv_rows
        if n > max_rows:
            raise PlanError(f"La descarga tendría {n:,} filas; el máximo es {max_rows:,}. "
                            "Usa un rango de fechas o un área menor.")
        sql = f"SELECT {', '.join(CSV_COLUMNS)} FROM ev {where} ORDER BY fecha_utc, hora"
        return sql, params
