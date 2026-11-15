"""¿Sirve el clima de Meteomatics para ANTICIPAR el fuego en Cusco? (análisis exploratorio)

Uso (desde la raíz del repo, con los datos de descargar.py en datos/):
    python -I -X utf8 exploratorio/meteomatics/preventivo.py

A diferencia de explorar.py (clima y fuego del MISMO periodo), aquí el clima siempre es ANTERIOR
al fuego que se quiere anticipar, y cada resultado se compara con lo que se sabría sin clima:

A. Semana siguiente (8 puntos, jun-nov): anomalía del clima de la semana s frente a la anomalía
   del fuego de la semana s+1. Referencia: persistencia (el fuego de la semana s).
B. Mes siguiente (8 puntos, objetivo jul-oct): clima del mes m frente al fuego del mes m+1.
   Referencia: persistencia (fuego del mes m).
C. Temporada (Cusco y 8 puntos, 2003-2025): clima de antes del 30 de junio frente al fuego de
   jul-oct. Prueba de acierto dejando un año fuera: ¿acierta el tercil (bajo / normal / alto)
   mejor que el azar (33 %) y que la persistencia (tercil de la temporada anterior)?

Significancia: permutación por bloques de años (se barajan años completos, no semanas: el fuego y
el clima de semanas vecinas no son independientes) y corrección de Benjamini-Hochberg por las
muchas pruebas. Regla del equipo (MAESTRO §1.9, sequia_fuego/PROTOCOLO.md): nada de esto es un
hallazgo confirmado; Cusco ya se exploró. Salida: resultados/PREVENTIVO.md, preventivo.csv y
preventivo.png (solo coeficientes y figuras: los datos de Meteomatics no se publican).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[1]
DATOS, RES = AQUI / "datos", AQUI / "resultados"
CELDA_DIA = ROOT / "data" / "harmonized" / "harmonizado_cusco_celda_dia.csv"
PASO, ANIOS = 0.5, range(2003, 2026)
RNG = np.random.default_rng(20261114)
N_PERM = 1000

VARS = {  # columna de la API -> (nombre, agregación, etiqueta)
    "fosberg_fire_weather_index:idx": ("fosberg", "mean", "Índice de Fosberg"),
    "forest_fire_warning:idx": ("aviso_incendio", "mean", "Aviso de incendio forestal (Meteomatics)"),
    "drought_index:idx": ("indice_sequia", "mean", "Índice de sequía"),
    "soil_moisture_deficit:mm": ("deficit_suelo", "mean", "Déficit de humedad del suelo"),
    "soil_moisture_index_-15cm:idx": ("humedad_suelo", "mean", "Humedad del suelo a 15 cm"),
    "vapor_pressure_deficit_2m:hPa": ("vpd", "mean", "Déficit de presión de vapor"),
    "evapotranspiration_24h:mm": ("evapotranspiracion", "sum", "Evapotranspiración"),
    "wind_gusts_10m_24h:ms": ("rachas", "max", "Racha máxima"),
    "precip_24h:mm": ("lluvia", "sum", "Lluvia"),
    "t_max_2m_24h:C": ("t_max", "mean", "Temperatura máxima"),
}
CORTOS = [v[0] for v in VARS.values()]
AGG = {v[0]: v[1] for v in VARS.values()}
ETQ = {v[0]: v[2] for v in VARS.values()} | {"persistencia": "Persistencia (fuego del periodo previo)"}


# ------------------------------------------------------------------ datos
def clima_diario(puntos: pd.DataFrame) -> pd.DataFrame:
    out = []
    for p in puntos["punto"]:
        archivos = sorted(DATOS.glob(f"{p}_*.csv"))
        if not archivos:
            raise SystemExit(f"Faltan datos de {p}: corre primero descargar.py")
        d = pd.concat([pd.read_csv(f, sep=";") for f in archivos], ignore_index=True)
        d["fecha"] = pd.to_datetime(d["validdate"]).dt.tz_localize(None).dt.normalize()
        out.append(d.rename(columns={k: v[0] for k, v in VARS.items()})
                   .assign(punto=p)[["punto", "fecha", *CORTOS]])
    return pd.concat(out, ignore_index=True)


def fuego_diario(puntos: pd.DataFrame) -> pd.DataFrame:
    cd = pd.read_csv(CELDA_DIA, dtype={"fecha_local": str})
    cd["fecha"] = pd.to_datetime(cd["fecha_local"].str[:10])
    cd = cd[cd["fecha"].dt.year.isin(ANIOS)]
    cd["clat"] = np.floor(cd["cell_lat"] / PASO) * PASO
    cd["clon"] = np.floor(cd["cell_lon"] / PASO) * PASO
    dias = pd.date_range(f"{ANIOS[0]}-01-01", f"{ANIOS[-1]}-12-31")
    out = []
    for _, p in puntos.iterrows():
        s = cd[np.isclose(cd["clat"], p.celda_lat) & np.isclose(cd["clon"], p.celda_lon)]
        s = s.groupby("fecha")["eq_hotspots"].sum().reindex(dias, fill_value=0.0)
        out.append(pd.DataFrame({"punto": p.punto, "fecha": dias, "focos": s.to_numpy()}))
    total = cd.groupby("fecha")["eq_hotspots"].sum().reindex(dias, fill_value=0.0)
    out.append(pd.DataFrame({"punto": "CUSCO", "fecha": dias, "focos": total.to_numpy()}))
    return pd.concat(out, ignore_index=True)


def por_periodo(clima: pd.DataFrame, fuego: pd.DataFrame, clave: str) -> pd.DataFrame:
    """Agrega clima y fuego por semana (bloques de 7 días desde el 1-ene) o por mes."""
    def k(df):
        f = df["fecha"]
        per = (f.dt.day_of_year - 1) // 7 + 1 if clave == "semana" else f.dt.month
        return df.assign(anio=f.dt.year, per=per.clip(upper=52 if clave == "semana" else 12))
    c = k(clima).groupby(["punto", "anio", "per"]).agg(AGG).reset_index()
    f = k(fuego).groupby(["punto", "anio", "per"])["focos"].sum().reset_index()
    return f.merge(c, on=["punto", "anio", "per"], how="left")


def anomalia(df: pd.DataFrame, col: str) -> pd.Series:
    """Diferencia con la mediana del mismo periodo del año en ese punto (quita la estación)."""
    return df[col] - df.groupby(["punto", "per"])[col].transform("median")


# ------------------------------------------------------------------ estadística
def rank(x: pd.Series) -> np.ndarray:
    return x.rank().to_numpy()


def rho(x, y) -> float:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 8:
        return np.nan
    return float(np.corrcoef(pd.Series(x[ok]).rank(), pd.Series(y[ok]).rank())[0, 1])


def rho_parcial(x, y, z) -> float:
    """Spearman de x con y descontando z (¿el clima agrega algo a la persistencia?)."""
    rxy, rxz, ryz = rho(x, y), rho(x, z), rho(y, z)
    return (rxy - rxz * ryz) / np.sqrt(max((1 - rxz ** 2) * (1 - ryz ** 2), 1e-12))


def p_bloques(df: pd.DataFrame, x: str, y: str, z: str | None = None) -> float:
    """p bilateral permutando el clima entre AÑOS completos (respeta la dependencia en el año)."""
    f = (lambda d: rho_parcial(d[x], d[y], d[z])) if z else (lambda d: rho(d[x], d[y]))
    df = df.reset_index(drop=True)
    obs = f(df)
    if not np.isfinite(obs):
        return np.nan
    # Tabla [año, punto/periodo] -> fila; cada año recibe el clima de otro año en el mismo
    # punto y periodo (se precalcula una vez; antes se rehacía con pandas en cada permutación).
    key = ["punto", "per"] if "per" in df else ["punto"]
    ya, anios = pd.factorize(df["anio"])
    kc, _ = pd.factorize(pd.MultiIndex.from_frame(df[key]))
    tabla = np.full((len(anios), kc.max() + 1), -1)
    tabla[ya, kc] = np.arange(len(df))
    xv = np.append(df[x].to_numpy(float), np.nan)           # índice -1 -> NaN
    yv, zv = df[y].to_numpy(float), (df[z].to_numpy(float) if z else None)
    g = (lambda v: rho_parcial(v, yv, zv)) if z else (lambda v: rho(v, yv))
    mas = 0
    for _ in range(N_PERM):
        mas += abs(g(xv[tabla[RNG.permutation(len(anios))[ya], kc]])) >= abs(obs)
    return (mas + 1) / (N_PERM + 1)


def bh(p: pd.Series) -> pd.Series:
    """Benjamini-Hochberg: p ajustado por el número de pruebas."""
    orden = p.sort_values()
    m = len(orden)
    q = (orden * m / np.arange(1, m + 1))[::-1].cummin()[::-1].clip(upper=1)
    return q.reindex(p.index)


# ------------------------------------------------------------------ análisis
def adelanto(tabla: pd.DataFrame, meses_obj: list[int] | None, etiqueta: str) -> list[dict]:
    """Clima del periodo t frente al fuego del periodo t+1, en cada punto (sin CUSCO)."""
    t = tabla[tabla["punto"] != "CUSCO"].sort_values(["punto", "anio", "per"]).copy()
    t["focos_log"] = np.log1p(t["focos"])
    t["y"] = anomalia(t, "focos_log").groupby(t["punto"]).shift(-1)       # fuego de t+1
    t["persistencia"] = anomalia(t, "focos_log")                          # fuego de t
    for c in CORTOS:
        t[c] = anomalia(t, c)
    if meses_obj is not None:                         # el periodo objetivo (t+1) en la temporada
        t = t[(t["per"] + 1).isin(meses_obj)]
    else:                                             # semanas 23-47 (≈ jun-nov)
        t = t[t["per"].between(22, 46)]
    t = t.dropna(subset=["y"]).reset_index(drop=True)
    filas = [{"escala": etiqueta, "variable": "persistencia", "rho": rho(t["persistencia"], t["y"]),
              "rho_parcial": np.nan, "p": p_bloques(t, "persistencia", "y"), "n": len(t)}]
    for c in CORTOS:
        filas.append({"escala": etiqueta, "variable": c, "rho": rho(t[c], t["y"]),
                      "rho_parcial": rho_parcial(t[c], t["y"], t["persistencia"]),
                      "p": p_bloques(t, c, "y", "persistencia"), "n": len(t)})
    return filas


def predictores_temporada(mensual: pd.DataFrame) -> pd.DataFrame:
    """Lo que se sabe el 30 de junio, por punto y año, y el fuego de jul-oct que viene."""
    m = mensual.copy()
    lluvia_previa = (m.assign(anio_temp=np.where(m["per"] >= 11, m["anio"] + 1, m["anio"]))
                     .query("per >= 11 or per <= 3")
                     .groupby(["punto", "anio_temp"])["lluvia"].sum()
                     .rename_axis(["punto", "anio"]).rename("lluvia_nov_mar"))
    g = m.groupby(["punto", "anio"])
    def media(meses, col):
        return m[m["per"].isin(meses)].groupby(["punto", "anio"])[col].mean()
    pred = pd.DataFrame({
        "lluvia_nov_mar": lluvia_previa,
        "lluvia_abr_jun": m[m["per"].isin([4, 5, 6])].groupby(["punto", "anio"])["lluvia"].sum(),
        "humedad_suelo_jun": media([6], "humedad_suelo"),
        "deficit_suelo_jun": media([6], "deficit_suelo"),
        "indice_sequia_jun": media([6], "indice_sequia"),
        "vpd_may_jun": media([5, 6], "vpd"),
        "aviso_incendio_may_jun": media([5, 6], "aviso_incendio"),
        "fosberg_may_jun": media([5, 6], "fosberg"),
    })
    fuego = m[m["per"].isin([7, 8, 9, 10])].groupby(["punto", "anio"])["focos"].sum()
    pred["fuego_jul_oct"] = fuego
    pred["fuego_prev"] = fuego.groupby(level=0).shift(1)                 # temporada anterior
    del g
    return pred.reset_index().query("anio >= 2004")                      # nov-mar necesita 2003


def tercil_loo(d: pd.DataFrame, x: str) -> float:
    """Acierto del tercil del fuego dejando un año fuera (regresión lineal en rangos)."""
    d = d.dropna(subset=[x, "fuego_jul_oct"])
    aciertos = []
    for a in d["anio"]:
        tr, te = d[d["anio"] != a], d[d["anio"] == a]
        if tr[x].isna().any() or te[x].isna().any():
            continue
        cortes = tr["fuego_jul_oct"].quantile([1 / 3, 2 / 3]).to_numpy()
        b = np.polyfit(tr[x], tr["fuego_jul_oct"], 1)
        pred = np.polyval(b, te[x].iloc[0])
        real = te["fuego_jul_oct"].iloc[0]
        aciertos.append(np.searchsorted(cortes, pred) == np.searchsorted(cortes, real))
    return float(np.mean(aciertos)) if aciertos else np.nan


def temporada(pred: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    cols = [c for c in pred.columns if c not in ("punto", "anio", "fuego_jul_oct")]
    cus = pred[pred["punto"] == "CUSCO"].reset_index(drop=True)
    pts = pred[pred["punto"] != "CUSCO"].copy()
    for c in [*cols, "fuego_jul_oct"]:                 # anomalía por punto (log para el fuego)
        v = np.log1p(pts[c]) if c.startswith("fuego") else pts[c]
        pts[c] = v - v.groupby(pts["punto"]).transform("median")
    filas = []
    for c in cols:
        filas.append({"escala": "temporada (Cusco, 1 serie)", "variable": c,
                      "rho": rho(cus[c], cus["fuego_jul_oct"]), "rho_parcial": np.nan,
                      "p": p_bloques(cus.dropna(subset=[c, "fuego_jul_oct"]), c, "fuego_jul_oct"),
                      "n": int((cus[c].notna() & cus["fuego_jul_oct"].notna()).sum()),
                      "acierto_tercil": tercil_loo(cus, c)})
        filas.append({"escala": "temporada (8 puntos)", "variable": c,
                      "rho": rho(pts[c], pts["fuego_jul_oct"]), "rho_parcial": np.nan,
                      "p": p_bloques(pts.dropna(subset=[c]), c, "fuego_jul_oct"),
                      "n": int(pts[c].notna().sum())})
    return filas, cus


# ------------------------------------------------------------------ salida
def figura(res: pd.DataFrame, cus: pd.DataFrame, mejor: str) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.6))
    for i, (esc, color) in enumerate([("semana siguiente", "#1d79ad"), ("mes siguiente", "#e07b39")]):
        d = res[res["escala"] == esc].set_index("variable")
        v = d["rho_parcial"].fillna(d["rho"]).sort_values()
        ax[0].barh(np.arange(len(v)) + i * 0.4, v, height=0.4, color=color, label=esc)
        if i == 0:
            ax[0].set_yticks(np.arange(len(v)) + 0.2, [ETQ[k] for k in v.index], fontsize=8)
    ax[0].axvline(0, color="#444", lw=0.8)
    ax[0].set_xlabel("rho de Spearman (clima: parcial, descontando la persistencia)")
    ax[0].set_title("¿El clima de antes agrega algo al fuego reciente?", fontsize=10)
    ax[0].legend(fontsize=8)
    ax[1].scatter(cus[mejor], cus["fuego_jul_oct"], color="#c0392b")
    for _, r in cus.iterrows():
        ax[1].annotate(str(int(r.anio))[2:], (r[mejor], r.fuego_jul_oct), fontsize=7,
                       xytext=(3, 2), textcoords="offset points")
    ax[1].set_xlabel(mejor.replace("_", " "))
    ax[1].set_ylabel("Focos armonizados jul-oct (Cusco)")
    ax[1].set_title("Temporada: el predictor climático con mayor |rho| (30 de junio)", fontsize=10)
    fig.tight_layout()
    fig.savefig(RES / "preventivo.png", dpi=130)


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    puntos = pd.read_csv(AQUI / "puntos.csv")
    clima = clima_diario(puntos)
    # Cusco = promedio de los puntos ponderado por su parte del fuego (como explorar.py)
    w = puntos.set_index("punto")["parte_del_fuego"]
    cw = clima.assign(w=clima["punto"].map(w))
    cus = cw.groupby("fecha").apply(lambda g: pd.Series({c: np.average(g[c], weights=g["w"])
                                                         for c in CORTOS}), include_groups=False)
    clima = pd.concat([clima, cus.reset_index().assign(punto="CUSCO")], ignore_index=True)
    fuego = fuego_diario(puntos)

    semanal = por_periodo(clima, fuego, "semana")
    mensual = por_periodo(clima, fuego, "mes")
    filas = adelanto(semanal, None, "semana siguiente")
    filas += adelanto(mensual, [7, 8, 9, 10], "mes siguiente")
    f_temp, cus_t = temporada(predictores_temporada(mensual))
    filas += f_temp
    res = pd.DataFrame(filas)
    res["p_ajustado"] = bh(res["p"])
    res["etiqueta"] = res["variable"].map(lambda v: ETQ.get(v, v.replace("_", " ")))
    res.round(3).to_csv(RES / "preventivo.csv", index=False)

    temp_cus = res[(res["escala"] == "temporada (Cusco, 1 serie)")
                   & (res["variable"] != "fuego_prev")].dropna(subset=["rho"])
    mejor = temp_cus.loc[temp_cus["rho"].abs().idxmax(), "variable"]
    figura(res, cus_t, mejor)
    # persistencia de la temporada como referencia del acierto de terciles
    acierto_persist = tercil_loo(cus_t, "fuego_prev")
    print(res.round(3).to_string())
    print("acierto tercil persistencia:", round(acierto_persist, 3))


if __name__ == "__main__":
    main()
