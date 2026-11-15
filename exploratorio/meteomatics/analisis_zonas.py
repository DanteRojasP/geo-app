"""Meteomatics por zonas homogéneas (clusterización con DEM y clima) frente al fuego de Cusco.

Exploratorio (MAESTRO §1.9; sequia_fuego/PROTOCOLO.md): no es un hallazgo ni un pronóstico.

1. Zonas: las 99 celdas de 0,25° (~28 km) de Cusco (exploratorio/preventivo/linea_base.py).
2. Relieve (DEM SRTM, harmonizacion/cusco_ref/elev.npy, 0,01°): altitud media, rugosidad, pendiente y
   fracción sobre 3.500 m y bajo 1.500 m de cada zona.
3. Clima (Meteomatics 2003-2025, datos/zonas/): lluvia anual, parte de la lluvia en dic-mar, déficit de
   presión de vapor, temperatura máxima e índice de Fosberg de la temporada seca (jun-oct).
4. Agrupamiento: k-means sobre relieve + clima estandarizados. El fuego NO entra (si entrara, los grupos
   reflejarían el resultado). k de 2 a 8, elegido por el coeficiente de silueta.
5. Análisis actual: por grupo, anomalía mensual del clima frente a la del fuego en jul-oct (mismo mes),
   Spearman con intervalo por bootstrap de años.
6. Análisis preventivo: escalera del protocolo preventivo (§8), dejando un año fuera:
     M2  calendario + fuego reciente (referencia)
     M3o M2 + clima de la semana ANTERIOR, ya observado (lo realista), pendiente distinta por grupo
     M3p M2 + clima de la MISMA semana (pronóstico perfecto: el techo)
   Métricas: habilidad de Brier (BSS) frente a M2, IC 90 % por años, años en que mejora, peor año, AUC y
   captura del 10 % superior. Criterios de aceptación de PROTOCOLO_PREVENTIVO.md §9.2.
   Sensibilidad: sin las semanas con días sin VIIRS S-NPP (revisar_antonio.md), si se pasa la carpeta de FIRMS.

Uso (desde la raíz del repo):
    python -I -X utf8 exploratorio/meteomatics/analisis_zonas.py [carpeta_firms_peru_raw]
Salidas en exploratorio/meteomatics/resultados/: ZONAS_salida.txt (por consola), zonas_grupos.csv
(zona -> grupo), zonas_preventivo.csv y zonas_clusters.png. No se publican datos crudos de Meteomatics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score, silhouette_score
from sklearn.preprocessing import StandardScaler

matplotlib.use("Agg")
import matplotlib.pyplot as plt

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[1]
sys.path.insert(0, str(AQUI.parent / "preventivo"))
import linea_base as lb

DATOS, RES = AQUI / "datos" / "zonas", AQUI / "resultados"
REF = ROOT / "harmonizacion" / "cusco_ref"
PASO = 0.25
ANIOS = lb.ANIOS
RNG = np.random.default_rng(20261115)
COLS = {"fosberg_fire_weather_index:idx": "fosberg", "forest_fire_warning:idx": "aviso",
        "drought_index:idx": "sequia", "soil_moisture_deficit:mm": "deficit_suelo",
        "soil_moisture_index_-15cm:idx": "humedad_suelo", "vapor_pressure_deficit_2m:hPa": "vpd",
        "evapotranspiration_24h:mm": "evapo", "wind_gusts_10m_24h:ms": "racha",
        "precip_24h:mm": "lluvia", "t_max_2m_24h:C": "tmax"}
AGG = {"fosberg": "mean", "aviso": "mean", "sequia": "mean", "deficit_suelo": "mean", "humedad_suelo": "mean",
       "vpd": "mean", "evapo": "sum", "racha": "max", "lluvia": "sum", "tmax": "mean"}
# Variables del modelo preventivo: pocas, para no sobreajustar con 23 años.
VARS_PREV = ["lluvia", "vpd", "fosberg", "humedad_suelo"]
ETQ = {"fosberg": "Índice de Fosberg", "aviso": "Aviso de incendio forestal", "sequia": "Índice de sequía",
       "deficit_suelo": "Déficit de humedad del suelo", "humedad_suelo": "Humedad del suelo a 15 cm",
       "vpd": "Déficit de presión de vapor", "evapo": "Evapotranspiración", "racha": "Racha máxima",
       "lluvia": "Lluvia", "tmax": "Temperatura máxima"}


# ------------------------------------------------------------------ datos
def clima_diario() -> pd.DataFrame:
    fs = sorted(DATOS.glob("z_*.csv"))
    if len(fs) < len(ANIOS):
        sys.exit(f"Faltan años de Meteomatics ({len(fs)} de {len(ANIOS)}): corre descargar_zonas.py")
    d = pd.concat([pd.read_csv(f, sep=";") for f in fs], ignore_index=True).rename(columns=COLS)
    d["fecha"] = pd.to_datetime(d["validdate"]).dt.tz_localize(None).dt.normalize()
    d["zi"] = np.floor(d["lat"] / PASO).astype(int)
    d["zj"] = np.floor(d["lon"] / PASO).astype(int)
    return d.drop(columns=["validdate"])


def relieve(z: pd.DataFrame) -> pd.DataFrame:
    meta = json.loads((REF / "meta.json").read_text(encoding="utf-8"))
    el = np.load(REF / "elev.npy")
    p, lon0, lat1 = meta["paso"], meta["lon0"], meta["lat1"]
    ny, nx = el.shape
    lat_c = lat1 - (np.arange(ny) + 0.5) * p
    lon_c = lon0 + (np.arange(nx) + 0.5) * p
    # Pendiente en grados con el tamaño real de la celda (m).
    dy = p * 111_320.0
    dx = p * 111_320.0 * np.cos(np.radians(lat_c))[:, None]
    gy, gx = np.gradient(el)
    pend = np.degrees(np.arctan(np.hypot(gx / dx, gy / dy)))
    zi = np.floor(lat_c / PASO).astype(int)[:, None].repeat(nx, 1)
    zj = np.floor(lon_c / PASO).astype(int)[None, :].repeat(ny, 0)
    df = pd.DataFrame({"zi": zi.ravel(), "zj": zj.ravel(), "el": el.ravel(), "pend": pend.ravel()})
    g = df.groupby(["zi", "zj"]).agg(alt_media=("el", "mean"), rugosidad=("el", "std"),
                                     pendiente=("pend", "mean"),
                                     sobre_3500=("el", lambda s: (s >= 3500).mean()),
                                     bajo_1500=("el", lambda s: (s < 1500).mean())).reset_index()
    return z.merge(g, on=["zi", "zj"], how="left")


def climatologia(d: pd.DataFrame) -> pd.DataFrame:
    d = d[d["fecha"].dt.year.isin(ANIOS)]
    m = d["fecha"].dt.month
    anual = d.groupby(["zi", "zj", d["fecha"].dt.year])["lluvia"].sum().groupby(["zi", "zj"]).mean()
    humeda = d[m.isin([12, 1, 2, 3])].groupby(["zi", "zj"])["lluvia"].sum() / d.groupby(["zi", "zj"])["lluvia"].sum()
    seca = d[m.isin([6, 7, 8, 9, 10])].groupby(["zi", "zj"])[["vpd", "tmax", "fosberg"]].mean()
    return pd.concat([anual.rename("lluvia_anual"), humeda.rename("parte_lluvia_dic_mar"),
                      seca.add_suffix("_seca")], axis=1).reset_index()


def semanal(d: pd.DataFrame) -> pd.DataFrame:
    f = d["fecha"]
    d = d.assign(anio=f.dt.year, sem=((f.dt.day_of_year - 1) // 7 + 1).clip(upper=52))
    return d.groupby(["zi", "zj", "anio", "sem"]).agg(AGG).reset_index()


def huecos_viirs(raw: Path | None) -> set:
    if raw is None or not raw.is_dir():
        return set()
    v = pd.concat([pd.read_csv(f, usecols=["acq_date"]) for f in sorted(raw.glob("viirs-snpp_*_Peru.csv"))])
    dias = set(pd.to_datetime(v["acq_date"]).dt.normalize())
    out = set()
    for d in pd.date_range("2013-01-01", "2025-12-31"):
        if d not in dias:
            out.add((d.year, min((d.day_of_year - 1) // 7 + 1, 52)))
    return out


# ------------------------------------------------------------------ 1-4. grupos
def agrupar(z: pd.DataFrame) -> tuple[pd.DataFrame, list, list]:
    feats = ["alt_media", "rugosidad", "pendiente", "sobre_3500", "bajo_1500", "lluvia_anual",
             "parte_lluvia_dic_mar", "vpd_seca", "tmax_seca", "fosberg_seca"]
    x = StandardScaler().fit_transform(z[feats])
    sil = []
    for k in range(2, 9):
        lab = KMeans(k, n_init=50, random_state=0).fit_predict(x)
        sil.append((k, silhouette_score(x, lab)))
    k_mejor = max(sil, key=lambda t: t[1])[0]
    km = KMeans(k_mejor, n_init=50, random_state=0).fit(x)
    # Orden de los grupos por altitud media (1 = el más bajo), para nombrarlos de forma estable.
    orden = z.assign(c=km.labels_).groupby("c")["alt_media"].mean().sort_values().index
    mapa = {c: i + 1 for i, c in enumerate(orden)}
    z = z.assign(grupo=[mapa[c] for c in km.labels_])
    return z, feats, sil


# ------------------------------------------------------------------ 5. análisis actual
def actual(t: pd.DataFrame, wk: pd.DataFrame, z: pd.DataFrame) -> pd.DataFrame:
    """Por grupo: anomalía mensual (jul-oct) del clima frente a la del fuego, mismo mes."""
    fuego = t.merge(z[["zi", "zj", "grupo"]], on=["zi", "zj"])
    clim = wk.merge(z[["zi", "zj", "grupo"]], on=["zi", "zj"])
    # semana -> mes aproximado (semana 1 = enero): mes del día central de la semana
    mes = lambda s: pd.to_datetime("2001-01-01") + pd.to_timedelta((s - 1) * 7 + 3, unit="D")
    fuego["mes"] = mes(fuego["sem"]).dt.month
    clim["mes"] = mes(clim["sem"]).dt.month
    filas = []
    grupos = sorted(z["grupo"].unique())
    for g in [*grupos, "Cusco"]:
        f = fuego if g == "Cusco" else fuego[fuego["grupo"] == g]
        c = clim if g == "Cusco" else clim[clim["grupo"] == g]
        fm = f.groupby(["anio", "mes"])["n"].sum()
        cm = c.groupby(["anio", "mes"]).agg({v: ("sum" if AGG[v] == "sum" else "mean") for v in AGG})
        df = cm.join(np.log1p(fm).rename("fuego"), how="inner").reset_index()
        df = df[df["mes"].isin([7, 8, 9, 10]) & df["anio"].isin(ANIOS)]
        an = df.groupby("mes").transform(lambda s: s - s.median())
        an["anio"] = df["anio"]
        for v in AGG:
            r = an[[v, "fuego"]].rank().corr().iloc[0, 1]
            boot = []
            anios = an["anio"].unique()
            for _ in range(1000):
                sel = RNG.choice(anios, len(anios))
                b = pd.concat([an[an["anio"] == a] for a in sel])
                boot.append(b[[v, "fuego"]].rank().corr().iloc[0, 1])
            filas.append({"grupo": g, "variable": v, "rho": r, "ic_bajo": np.nanquantile(boot, 0.05),
                          "ic_alto": np.nanquantile(boot, 0.95), "n_meses": len(an)})
    return pd.DataFrame(filas)


# ------------------------------------------------------------------ 6. análisis preventivo
def preventivo(t: pd.DataFrame, wk: pd.DataFrame, z: pd.DataFrame, huecos: set) -> tuple[pd.DataFrame, dict]:
    t = t.merge(z[["zi", "zj", "grupo"]], on=["zi", "zj"])
    w = wk[["zi", "zj", "anio", "sem", *VARS_PREV]]
    t = t.merge(w.add_suffix("_p").rename(columns={"zi_p": "zi", "zj_p": "zj", "anio_p": "anio", "sem_p": "sem"}),
                on=["zi", "zj", "anio", "sem"], how="left")                       # misma semana (techo)
    w_ant = w.assign(sem=w["sem"] + 1)                                              # semana anterior -> fila objetivo
    t = t.merge(w_ant.add_suffix("_o").rename(columns={"zi_o": "zi", "zj_o": "zj", "anio_o": "anio", "sem_o": "sem"}),
                on=["zi", "zj", "anio", "sem"], how="left")
    obj = t[t["sem"].isin(lb.SEMANAS)].copy()
    grupos = sorted(z["grupo"].unique())
    marca = obj.apply(lambda r: (r["anio"], r["sem"]) in huecos or (r["anio"], r["sem"] - 1) in huecos, axis=1) \
        if huecos else pd.Series(False, index=obj.index)
    obj["hueco"] = marca.to_numpy()
    filas = []
    for a in ANIOS:
        tr_all, te = t[t["anio"] != a], obj[obj["anio"] == a].copy()
        tr = obj[obj["anio"] != a].copy()
        clim = lb.calendario(tr_all)
        tr, te = tr.join(clim, on=["zi", "zj", "sem"]), te.join(clim, on=["zi", "zj", "sem"])
        # anomalías estandarizadas por zona y semana del año, SOLO con los años de ajuste
        for suf in ("_p", "_o"):
            for v in VARS_PREV:
                col = v + suf
                ref = tr.groupby(["zi", "zj", "sem"])[col].agg(["mean", "std"])
                for d in (tr, te):
                    j = d.join(ref, on=["zi", "zj", "sem"])
                    d[col + "_z"] = ((j[col] - j["mean"]) / j["std"].replace(0, np.nan)).fillna(0).clip(-4, 4)

        def x_base(d):
            return np.column_stack([np.log(d["clim"] / (1 - d["clim"])), d["y_prev"], d["n_prev"],
                                    d["vec_prev"], d["reg_prev"]])

        def x_clima(d, suf):
            cols = [x_base(d)]
            for g in grupos:                                   # pendiente distinta por grupo
                m = (d["grupo"] == g).to_numpy()[:, None]
                cols.append(d[[v + suf + "_z" for v in VARS_PREV]].to_numpy() * m)
            return np.column_stack(cols)

        p = {}
        p["M2"] = LogisticRegression(max_iter=1000).fit(x_base(tr), tr["y"]).predict_proba(x_base(te))[:, 1]
        for nombre, suf in (("M3o", "_o"), ("M3p", "_p")):
            m = LogisticRegression(max_iter=1000, C=0.5).fit(x_clima(tr, suf), tr["y"])
            p[nombre] = m.predict_proba(x_clima(te, suf))[:, 1]
        te = te.assign(**{f"p_{k}": v for k, v in p.items()})
        filas.append(te[["zi", "zj", "anio", "sem", "grupo", "hueco", "y", "p_M2", "p_M3o", "p_M3p"]])
    r = pd.concat(filas, ignore_index=True)

    def resumen(d: pd.DataFrame, modelo: str) -> dict:
        bs = d.groupby("anio").apply(lambda g: pd.Series({
            "ref": np.mean((g["p_M2"] - g["y"]) ** 2), "mod": np.mean((g[f"p_{modelo}"] - g["y"]) ** 2)}),
            include_groups=False)
        bss = 1 - bs["mod"].mean() / bs["ref"].mean()
        boot = [1 - bs["mod"].to_numpy()[i].mean() / bs["ref"].to_numpy()[i].mean()
                for i in RNG.integers(0, len(bs), size=(4000, len(bs)))]
        por_anio = 1 - bs["mod"] / bs["ref"]
        top = d[f"p_{modelo}"] >= d[f"p_{modelo}"].quantile(0.9)
        top2 = d["p_M2"] >= d["p_M2"].quantile(0.9)
        return {"bss": bss, "ic_bajo": np.quantile(boot, 0.05), "ic_alto": np.quantile(boot, 0.95),
                "anios_mejora": int((por_anio > 0).sum()), "peor": float(por_anio.min()),
                "peor_anio": int(por_anio.idxmin()),
                "auc_m2": roc_auc_score(d["y"], d["p_M2"]), "auc": roc_auc_score(d["y"], d[f"p_{modelo}"]),
                "captura_m2": d.loc[top2, "y"].sum() / d["y"].sum(), "captura": d.loc[top, "y"].sum() / d["y"].sum(),
                "pendiente_calibracion": _calib(d["y"], d[f"p_{modelo}"])}

    out = []
    for modelo in ("M3o", "M3p"):
        for nombre, d in [("Cusco", r), ("Cusco sin semanas con hueco VIIRS", r[~r["hueco"]]),
                          *[(f"Grupo {g}", r[r["grupo"] == g]) for g in grupos]]:
            if len(d) == 0 or d["y"].nunique() < 2:
                continue
            out.append({"modelo": modelo, "conjunto": nombre, **resumen(d, modelo)})
    return pd.DataFrame(out), {"filas": len(r), "huecos": int(r["hueco"].sum())}


def _calib(y, p) -> float:
    lg = np.log(np.clip(p, 1e-6, 1 - 1e-6) / (1 - np.clip(p, 1e-6, 1 - 1e-6)))
    return float(LogisticRegression(C=1e6, max_iter=1000).fit(lg.to_numpy().reshape(-1, 1), y).coef_[0, 0])


def criterio(row) -> str:
    ok = (row["bss"] >= 0.02 and row["ic_bajo"] > 0 and row["anios_mejora"] >= 16 and row["peor"] >= -0.05
          and 0.8 <= row["pendiente_calibracion"] <= 1.2 and row["captura"] >= row["captura_m2"] - 1e-9)
    return "PASA" if ok else "no pasa"


# ------------------------------------------------------------------ salida
def figura(z: pd.DataFrame, prev: pd.DataFrame) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(13, 5.2))
    cm = plt.get_cmap("tab10")
    for g, d in z.groupby("grupo"):
        ax[0].scatter(d["lon"], d["lat"], s=230, marker="s", color=cm(g - 1), label=f"Grupo {g}")
    ax[0].set_aspect("equal")
    ax[0].set_title("Zonas de ~28 km agrupadas por relieve y clima (sin usar el fuego)", fontsize=10)
    ax[0].legend(fontsize=8, loc="lower left")
    d = prev[prev["conjunto"].str.startswith(("Cusco", "Grupo"))]
    etiquetas = d["conjunto"].unique()
    xpos = np.arange(len(etiquetas))
    for i, (modelo, color) in enumerate((("M3o", "#1d79ad"), ("M3p", "#e07b39"))):
        s = d[d["modelo"] == modelo].set_index("conjunto").reindex(etiquetas)
        ax[1].bar(xpos + i * 0.38, s["bss"], width=0.38, color=color,
                  label={"M3o": "clima ya observado (realista)", "M3p": "clima de la misma semana (techo)"}[modelo])
        ax[1].errorbar(xpos + i * 0.38, s["bss"], yerr=[s["bss"] - s["ic_bajo"], s["ic_alto"] - s["bss"]],
                       fmt="none", ecolor="#333", capsize=3, lw=0.8)
    ax[1].axhline(0, color="#444", lw=0.8)
    ax[1].axhline(0.02, color="#c0392b", lw=0.8, ls="--", label="umbral del protocolo (+0,02)")
    ax[1].set_xticks(xpos + 0.19, [e.replace("Cusco sin semanas con hueco VIIRS", "Cusco sin\nhuecos VIIRS")
                                   for e in etiquetas], fontsize=8)
    ax[1].set_ylabel("Mejora frente a calendario + fuego reciente (BSS)")
    ax[1].set_title("¿Cuánto agrega el clima de Meteomatics a la semana siguiente?", fontsize=10)
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(RES / "zonas_clusters.png", dpi=130)


def main() -> None:
    raw = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    RES.mkdir(parents=True, exist_ok=True)
    z = pd.read_csv(DATOS / "zonas.csv")
    d = clima_diario()
    z = relieve(z).merge(climatologia(d), on=["zi", "zj"])
    z, feats, sil = agrupar(z)
    t = lb.tabla(PASO)
    t = t[t[["zi", "zj"]].apply(tuple, axis=1).isin(set(zip(z["zi"], z["zj"], strict=True)))]
    fuego_zona = (t[t["anio"].isin(ANIOS)].groupby(["zi", "zj"])["n"].sum() / len(ANIOS)).rename("focos_por_anio")
    z = z.join(fuego_zona, on=["zi", "zj"])
    print("== 1. Agrupamiento (k-means sobre relieve + clima; el fuego no entra) ==")
    print("silueta por k:", ", ".join(f"k={k}: {s:.3f}" for k, s in sil))
    desc = z.groupby("grupo").agg(zonas=("zi", "size"), alt_media=("alt_media", "mean"),
                                  sobre_3500=("sobre_3500", "mean"), bajo_1500=("bajo_1500", "mean"),
                                  pendiente=("pendiente", "mean"), lluvia_anual=("lluvia_anual", "mean"),
                                  lluvia_dic_mar=("parte_lluvia_dic_mar", "mean"), vpd_seca=("vpd_seca", "mean"),
                                  tmax_seca=("tmax_seca", "mean"), focos_por_anio=("focos_por_anio", "sum"))
    desc["parte_del_fuego"] = desc["focos_por_anio"] / desc["focos_por_anio"].sum()
    desc["focos_por_zona_anio"] = desc["focos_por_anio"] / desc["zonas"]
    print(desc.round(2).to_string())
    z[["zi", "zj", "lat", "lon", "grupo"]].to_csv(RES / "zonas_grupos.csv", index=False)

    wk = semanal(d)
    print("\n== 2. Análisis actual: anomalía mensual jul-oct, mismo mes (Spearman, IC 90 % por años) ==")
    act = actual(t, wk, z)
    for g, s in act.groupby("grupo", sort=False):
        s = s.reindex(s["rho"].abs().sort_values(ascending=False).index).head(4)
        print(f"  {('Grupo ' + str(g)) if g != 'Cusco' else 'Cusco (99 zonas)'}: " + " | ".join(
            f"{ETQ[r.variable]} {r.rho:+.2f} [{r.ic_bajo:+.2f}, {r.ic_alto:+.2f}]" for r in s.itertuples()))
    act.round(3).to_csv(RES / "zonas_actual.csv", index=False)

    print("\n== 3. Análisis preventivo: semana siguiente, frente a calendario + fuego reciente (M2) ==")
    hu = huecos_viirs(raw)
    prev, info = preventivo(t, wk, z, hu)
    prev["veredicto"] = prev.apply(criterio, axis=1)
    print(f"  zonas-semana evaluadas: {info['filas']:,} (con hueco VIIRS: {info['huecos']:,})")
    for r in prev.itertuples():
        print(f"  {r.modelo} | {r.conjunto:34} BSS {r.bss:+.3f} [{r.ic_bajo:+.3f}, {r.ic_alto:+.3f}] | "
              f"mejora {r.anios_mejora}/23 | peor {r.peor:+.3f} ({r.peor_anio}) | AUC {r.auc_m2:.3f}->{r.auc:.3f} | "
              f"captura 10 % {100 * r.captura_m2:.0f}->{100 * r.captura:.0f} % | calib {r.pendiente_calibracion:.2f} | "
              f"{r.veredicto}")
    prev.round(4).to_csv(RES / "zonas_preventivo.csv", index=False)
    figura(z, prev)


if __name__ == "__main__":
    main()
