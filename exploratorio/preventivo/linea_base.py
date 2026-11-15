"""Línea de referencia para una evaluación preventiva: ¿cuánto anticipan ya nuestros propios datos?

Mide, sin clima ni fuentes externas, lo que cualquier modelo preventivo tendría que superar
(PROTOCOLO_PREVENTIVO.md §8 y §9). Exploratorio: no es un pronóstico ni un hallazgo.

Unidad: zona (celda de G grados dentro de Cusco) x semana (bloques de 7 días desde el 1 de enero),
temporada de junio a noviembre (semanas 22 a 48), años 2003-2025 (sin focos extrapolados).
Objetivo: la zona tiene al menos un foco armonizado en la semana s+1 ("semana con fuego").

Modelos, evaluados dejando un año fuera (se ajusta con 22 años y se prueba en el otro):
  M0  tasa media: la misma probabilidad para todas las zonas y semanas.
  M1  calendario: frecuencia histórica de esa zona en esa semana del año (ventana de +-1 semana).
  M2  calendario + fuego reciente: regresión logística con el calendario, si la zona tuvo fuego la
      semana anterior y cuántas zonas vecinas (y de todo Cusco) lo tuvieron.
Métricas: puntaje de Brier (error cuadrático de la probabilidad; menor es mejor), habilidad de Brier
(BSS: mejora relativa frente a otro modelo) y AUC (capacidad de ordenar zonas con y sin fuego).

Uso (desde la raíz del repo): python -I -X utf8 exploratorio/preventivo/linea_base.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from shapely import contains_xy
from shapely.geometry import shape
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
CELDA_DIA = ROOT / "data" / "harmonized" / "harmonizado_cusco_celda_dia.csv"
LIMITE = ROOT / "harmonizacion" / "cusco_ref" / "limite.json"
ANIOS = list(range(2003, 2026))
SEMANAS = range(22, 49)            # objetivo: semanas 22-48 (junio a noviembre)
RNG = np.random.default_rng(20261115)


def limite():
    g = json.loads(LIMITE.read_text(encoding="utf-8"))
    if "features" in g:
        g = g["features"][0]
    return shape(g.get("geometry", g))


def tabla(paso: float) -> pd.DataFrame:
    """Zona x año x semana con y (fuego esa semana) y las variables conocidas la semana anterior."""
    cd = pd.read_csv(CELDA_DIA, usecols=["fecha_local", "cell_lat", "cell_lon", "eq_hotspots"],
                     dtype={"fecha_local": str})
    f = pd.to_datetime(cd["fecha_local"].str[:10])
    cd = cd.assign(anio=f.dt.year, sem=((f.dt.day_of_year - 1) // 7 + 1).clip(upper=52),
                   zi=np.floor(cd["cell_lat"] / paso).astype(int),
                   zj=np.floor(cd["cell_lon"] / paso).astype(int))
    cd = cd[cd["anio"].isin(ANIOS)]
    # Universo de zonas: todas las que tocan Cusco (no solo las que tuvieron fuego).
    geom = limite()
    w, s, e, n = geom.bounds
    ii = np.arange(int(np.floor(s / paso)), int(np.floor(n / paso)) + 1)
    jj = np.arange(int(np.floor(w / paso)), int(np.floor(e / paso)) + 1)
    gi, gj = np.meshgrid(ii, jj, indexing="ij")
    dentro = contains_xy(geom, (gj + 0.5) * paso, (gi + 0.5) * paso)
    zonas = pd.DataFrame({"zi": gi[dentro], "zj": gj[dentro]})
    act = cd.groupby(["zi", "zj", "anio", "sem"])["eq_hotspots"].sum().rename("n").reset_index()
    idx = (zonas.merge(pd.DataFrame({"anio": ANIOS}), how="cross")
           .merge(pd.DataFrame({"sem": range(1, 53)}), how="cross"))
    t = idx.merge(act, how="left", on=["zi", "zj", "anio", "sem"]).fillna({"n": 0.0})
    t["y"] = (t["n"] > 0).astype(int)
    t = t.sort_values(["zi", "zj", "anio", "sem"]).reset_index(drop=True)
    g = t.groupby(["zi", "zj", "anio"], sort=False)
    t["y_prev"] = g["y"].shift(1).fillna(0)                       # fuego en la zona la semana anterior
    t["n_prev"] = np.log1p(g["n"].shift(1).fillna(0))
    # Fuego la semana anterior en las 8 zonas vecinas y en todo Cusco.
    clave = t.set_index(["zi", "zj", "anio", "sem"])["y"]
    vec = np.zeros(len(t))
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di or dj:
                k = pd.MultiIndex.from_arrays([t["zi"] + di, t["zj"] + dj, t["anio"], t["sem"] - 1])
                vec += clave.reindex(k).fillna(0).to_numpy()
    t["vec_prev"] = vec
    reg = t.groupby(["anio", "sem"])["y"].mean().rename("reg").reset_index()
    reg["sem"] += 1
    t = t.merge(reg.rename(columns={"reg": "reg_prev"}), how="left", on=["anio", "sem"]).fillna({"reg_prev": 0})
    return t


def calendario(train: pd.DataFrame) -> pd.Series:
    """Frecuencia de fuego por zona y semana del año, con ventana de +-1 semana y suavizado."""
    f = train.groupby(["zi", "zj", "sem"])["y"].agg(["sum", "count"]).reset_index()
    piv_s = f.pivot(index=["zi", "zj"], columns="sem", values="sum").fillna(0)
    piv_c = f.pivot(index=["zi", "zj"], columns="sem", values="count").fillna(0)
    s = piv_s.T.rolling(3, center=True, min_periods=1).sum().T
    c = piv_c.T.rolling(3, center=True, min_periods=1).sum().T
    base = train["y"].mean()
    p = (s + 2 * base) / (c + 2)                                  # suavizado hacia la tasa media
    return p.stack().rename("clim")


def evaluar(paso: float) -> dict:
    t = tabla(paso)
    obj = t[t["sem"].isin(SEMANAS)]
    filas = []
    for a in ANIOS:
        tr, te = obj[obj["anio"] != a], obj[obj["anio"] == a].copy()
        clim = calendario(t[t["anio"] != a])
        tr = tr.join(clim, on=["zi", "zj", "sem"])
        te = te.join(clim, on=["zi", "zj", "sem"])
        p0 = np.full(len(te), tr["y"].mean())
        p1 = te["clim"].to_numpy()
        x = lambda d: np.column_stack([np.log(d["clim"] / (1 - d["clim"])), d["y_prev"], d["n_prev"],
                                       d["vec_prev"], d["reg_prev"]])
        m = LogisticRegression(max_iter=500).fit(x(tr), tr["y"])
        p2 = m.predict_proba(x(te))[:, 1]
        y = te["y"].to_numpy()
        filas.append({"anio": a, "tasa": y.mean(), "bs0": np.mean((p0 - y) ** 2),
                      "bs1": np.mean((p1 - y) ** 2), "bs2": np.mean((p2 - y) ** 2),
                      "auc1": roc_auc_score(y, p1), "auc2": roc_auc_score(y, p2),
                      # ¿sirve como lista de atención? Del 10 % de zonas-semana con mayor probabilidad,
                      # qué parte tuvo fuego y qué parte de todo el fuego capturan.
                      **_decil(y, p1, "1"), **_decil(y, p2, "2")})
    r = pd.DataFrame(filas)
    bss10 = 1 - r["bs1"].mean() / r["bs0"].mean()
    bss21 = 1 - r["bs2"].mean() / r["bs1"].mean()
    por_anio = 1 - r["bs2"] / r["bs1"]
    boot = [1 - r["bs2"].to_numpy()[i].mean() / r["bs1"].to_numpy()[i].mean()
            for i in RNG.integers(0, len(r), size=(4000, len(r)))]
    return {"paso": paso, "zonas": int(obj.groupby(["zi", "zj"]).ngroups), "zonas_semana": len(obj),
            "tasa": r["tasa"].mean(), "bss_calendario_vs_media": bss10, "bss_reciente_vs_calendario": bss21,
            "ic90": (float(np.quantile(boot, 0.05)), float(np.quantile(boot, 0.95))),
            "anios_mejora": int((por_anio > 0).sum()), "peor_anio": (int(r.loc[por_anio.idxmin(), "anio"]),
                                                                    float(por_anio.min())),
            "auc1": r["auc1"].mean(), "auc2": r["auc2"].mean(),
            "acierto1": r["prec1"].mean(), "captura1": r["cap1"].mean(),
            "acierto2": r["prec2"].mean(), "captura2": r["cap2"].mean()}


def _decil(y: np.ndarray, p: np.ndarray, tag: str) -> dict:
    top = p >= np.quantile(p, 0.9)
    return {f"prec{tag}": y[top].mean(), f"cap{tag}": y[top].sum() / max(y.sum(), 1)}


def main() -> None:
    for paso, nombre in ((0.25, "zonas de ~28 km"), (0.10, "zonas de ~11 km")):
        r = evaluar(paso)
        print(f"== {nombre} ({r['zonas']} zonas, {r['zonas_semana']:,} zonas-semana, jun-nov 2003-2025) ==")
        print(f"   semanas con fuego: {100 * r['tasa']:.1f} %")
        print(f"   calendario frente a tasa media: BSS {r['bss_calendario_vs_media']:+.3f} | AUC {r['auc1']:.3f}")
        print(f"   + fuego reciente frente a calendario: BSS {r['bss_reciente_vs_calendario']:+.3f} "
              f"(IC 90 % por años {r['ic90'][0]:+.3f} a {r['ic90'][1]:+.3f}) | AUC {r['auc2']:.3f} | "
              f"mejora en {r['anios_mejora']} de {len(ANIOS)} años | peor año {r['peor_anio'][0]} "
              f"({r['peor_anio'][1]:+.3f})")
        print(f"   10 % de zonas-semana con mayor probabilidad: calendario acierta {100 * r['acierto1']:.0f} % y "
              f"captura {100 * r['captura1']:.0f} % del fuego | con fuego reciente acierta "
              f"{100 * r['acierto2']:.0f} % y captura {100 * r['captura2']:.0f} %")


if __name__ == "__main__":
    main()
