"""Comparación EXPLORATORIA: clima de Meteomatics frente a los focos armonizados de Cusco (2003-2025).

Uso (desde la raíz del repo, después de descargar.py):
    python -I -X utf8 exploratorio/meteomatics/explorar.py

Qué hace (todo descriptivo; ver la sección "Límites" del informe):
1. Pasa los datos diarios de cada punto a valores mensuales (media, suma o máximo según la variable)
   y arma un valor para Cusco ponderando cada punto por su parte del fuego.
2. Perfil estacional: mediana de cada mes del clima frente a la de los focos armonizados.
3. Meses: correlación de Spearman entre la ANOMALÍA mensual del clima y la de los focos (cada valor
   menos la mediana de su mes calendario), en todos los meses y solo en la temporada (jul-oct).
4. Rezagos: clima de 1 a 3 meses antes frente al fuego de la temporada.
5. Años: total de focos jul-oct frente al clima medio de jul-oct y de ene-jun (23 años).
6. Puntos: lo mismo que 3, pero con el fuego de la celda de 0.5° de cada punto.

Salidas: resultados/INFORME.md, resultados/*.png y resultados/correlaciones.csv (solo coeficientes:
los datos de Meteomatics no se publican). La tabla mensual completa queda en datos/ (ignorado por git).
Regla del equipo (MAESTRO §1.9 y harmonizacion/sequia_fuego/PROTOCOLO.md): nada de esto es un
hallazgo ni un pronóstico; los coeficientes orientan qué mirar después.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

AQUI = Path(__file__).resolve().parent
ROOT = AQUI.parents[1]
DATOS, RES = AQUI / "datos", AQUI / "resultados"
CELDA_DIA = ROOT / "data" / "harmonized" / "harmonizado_cusco_celda_dia.csv"
TEMPORADA = [7, 8, 9, 10]
PASO = 0.5

# variable de la API -> (nombre corto, cómo se agrega al mes, etiqueta)
VARS = {
    "fosberg_fire_weather_index:idx": ("fosberg", "mean", "Índice de Fosberg (0-100)"),
    "forest_fire_warning:idx": ("aviso_incendio", "mean", "Aviso de incendio forestal (0-1)"),
    "drought_index:idx": ("indice_sequia", "mean", "Índice de sequía (-4 a 4)"),
    "soil_moisture_deficit:mm": ("deficit_humedad_suelo", "mean", "Déficit de humedad del suelo (mm)"),
    "soil_moisture_index_-15cm:idx": ("humedad_suelo_15cm", "mean", "Humedad del suelo a 15 cm (índice)"),
    "vapor_pressure_deficit_2m:hPa": ("vpd", "mean", "Déficit de presión de vapor (hPa)"),
    "evapotranspiration_24h:mm": ("evapotranspiracion", "sum", "Evapotranspiración (mm/mes)"),
    "wind_gusts_10m_24h:ms": ("rachas_max", "max", "Racha máxima (m/s)"),
    "precip_24h:mm": ("lluvia", "sum", "Lluvia (mm/mes)"),
    "t_max_2m_24h:C": ("t_max", "mean", "Temperatura máxima (°C)"),
}
CORTOS = [v[0] for v in VARS.values()]
ETIQUETA = {v[0]: v[2] for v in VARS.values()}


def clima_mensual(puntos: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for p in puntos["punto"]:
        archivos = sorted(DATOS.glob(f"{p}_*.csv"))
        if not archivos:
            raise SystemExit(f"Faltan datos de {p}: corre primero descargar.py")
        d = pd.concat([pd.read_csv(f, sep=";") for f in archivos], ignore_index=True)
        d["fecha"] = pd.to_datetime(d["validdate"]).dt.tz_localize(None)
        d = d.rename(columns={k: v[0] for k, v in VARS.items()})
        d["anio"], d["mes"] = d["fecha"].dt.year, d["fecha"].dt.month
        agg = {v[0]: v[1] for v in VARS.values()}
        m = d.groupby(["anio", "mes"]).agg(agg).reset_index()
        m.insert(0, "punto", p)
        filas.append(m)
    return pd.concat(filas, ignore_index=True)


def fuego_mensual(puntos: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cd = pd.read_csv(CELDA_DIA, dtype={"fecha_local": str})
    cd["anio"] = cd["fecha_local"].str[:4].astype(int)
    cd["mes"] = cd["fecha_local"].str[5:7].astype(int)
    cd = cd[cd["anio"].between(2003, 2025)]
    idx = pd.MultiIndex.from_product([range(2003, 2026), range(1, 13)], names=["anio", "mes"])
    total = cd.groupby(["anio", "mes"])["eq_hotspots"].sum().reindex(idx, fill_value=0.0)
    cd["celda_lat"] = np.floor(cd["cell_lat"] / PASO) * PASO
    cd["celda_lon"] = np.floor(cd["cell_lon"] / PASO) * PASO
    por_punto = []
    for _, p in puntos.iterrows():
        sel = cd[np.isclose(cd["celda_lat"], p.celda_lat) & np.isclose(cd["celda_lon"], p.celda_lon)]
        s = sel.groupby(["anio", "mes"])["eq_hotspots"].sum().reindex(idx, fill_value=0.0)
        por_punto.append(s.rename("focos").reset_index().assign(punto=p.punto))
    return (total.rename("focos").reset_index(), pd.concat(por_punto, ignore_index=True))


def anomalia(df: pd.DataFrame, col: str, por: list[str]) -> pd.Series:
    """Valor menos la mediana de su mes calendario (quita el ciclo estacional)."""
    return df[col] - df.groupby(por + ["mes"])[col].transform("median")


def spearman(a: pd.Series, b: pd.Series) -> float:
    ok = a.notna() & b.notna()
    return float(a[ok].rank().corr(b[ok].rank())) if ok.sum() > 5 else np.nan


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    puntos = pd.read_csv(AQUI / "puntos.csv")
    clima = clima_mensual(puntos)
    total, fuego_p = fuego_mensual(puntos)

    # Clima de Cusco = promedio de los puntos ponderado por su parte del fuego.
    w = puntos.set_index("punto")["parte_del_fuego"]
    clima["w"] = clima["punto"].map(w)
    cusco = (clima.groupby(["anio", "mes"])
             .apply(lambda g: pd.Series({c: np.average(g[c], weights=g["w"]) for c in CORTOS}),
                    include_groups=False).reset_index())
    tabla = cusco.merge(total, on=["anio", "mes"])
    tabla.to_csv(DATOS / "tabla_mensual_cusco.csv", index=False)       # no se publica

    filas = []
    # 2. Perfil estacional (12 medianas).
    estac = tabla.groupby("mes")[CORTOS + ["focos"]].median()
    for c in CORTOS:
        filas.append({"analisis": "perfil estacional (12 meses)", "variable": c,
                      "rho": spearman(estac[c], estac["focos"]), "n": 12})
    # 3. Anomalías mensuales.
    tabla["focos_anom"] = anomalia(tabla, "focos", [])
    temporada = tabla["mes"].isin(TEMPORADA)
    for c in CORTOS:
        a = anomalia(tabla, c, [])
        filas.append({"analisis": "anomalía mensual, todos los meses", "variable": c,
                      "rho": spearman(a, tabla["focos_anom"]), "n": int(len(tabla))})
        filas.append({"analisis": "anomalía mensual, jul-oct", "variable": c,
                      "rho": spearman(a[temporada], tabla.loc[temporada, "focos_anom"]),
                      "n": int(temporada.sum())})
    # 4. Rezagos (clima de meses previos frente al fuego de jul-oct).
    orden = tabla.sort_values(["anio", "mes"]).reset_index(drop=True)
    t_ord = orden["mes"].isin(TEMPORADA)
    for c in ["lluvia", "indice_sequia", "deficit_humedad_suelo", "humedad_suelo_15cm", "vpd"]:
        a = anomalia(orden, c, [])
        for lag in (1, 2, 3):
            filas.append({"analisis": f"rezago {lag} mes(es), jul-oct", "variable": c,
                          "rho": spearman(a.shift(lag)[t_ord], orden.loc[t_ord, "focos_anom"]),
                          "n": int(t_ord.sum())})
    # 5. Años: fuego jul-oct frente al clima de jul-oct y de ene-jun.
    t = tabla[temporada].groupby("anio")
    anual = t[CORTOS].mean().join(t["focos"].sum())
    previo = tabla[tabla["mes"].between(1, 6)].groupby("anio")[CORTOS].mean()
    for c in CORTOS:
        filas.append({"analisis": "años: clima jul-oct vs fuego jul-oct", "variable": c,
                      "rho": spearman(anual[c], anual["focos"]), "n": int(len(anual))})
        filas.append({"analisis": "años: clima ene-jun vs fuego jul-oct", "variable": c,
                      "rho": spearman(previo[c], anual["focos"]), "n": int(len(anual))})
    # 6. Por punto (fuego de la celda de 0.5° del punto), jul-oct.
    pp = clima.merge(fuego_p, on=["punto", "anio", "mes"])
    pp["focos_anom"] = anomalia(pp, "focos", ["punto"])
    t_pp = pp["mes"].isin(TEMPORADA)
    for c in CORTOS:
        a = anomalia(pp, c, ["punto"])
        rhos = [spearman(a[t_pp & (pp["punto"] == p)], pp.loc[t_pp & (pp["punto"] == p), "focos_anom"])
                for p in puntos["punto"]]
        filas.append({"analisis": "por punto, anomalía jul-oct (mediana de 8)", "variable": c,
                      "rho": float(np.nanmedian(rhos)), "n": int(t_pp.sum())})
    corr = pd.DataFrame(filas)
    corr["rho"] = corr["rho"].round(2)
    corr.to_csv(RES / "correlaciones.csv", index=False)

    figuras(estac, tabla, anual, corr)
    informe(puntos, corr, estac, anual)
    print("OK: resultados/INFORME.md, correlaciones.csv y figuras")


def figuras(estac: pd.DataFrame, tabla: pd.DataFrame, anual: pd.DataFrame,
            corr: pd.DataFrame) -> None:
    meses = ["E", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"]
    sel = ["lluvia", "humedad_suelo_15cm", "vpd", "fosberg", "aviso_incendio", "t_max"]
    fig, axes = plt.subplots(2, 3, figsize=(13, 7), sharex=True)
    for ax, c in zip(axes.flat, sel, strict=True):
        ax.bar(range(1, 13), estac["focos"], color="#fd8d3c", alpha=0.55, label="focos armonizados")
        ax2 = ax.twinx()
        ax2.plot(range(1, 13), estac[c], color="#31688e", marker="o", lw=2, label=ETIQUETA[c])
        ax.set_title(ETIQUETA[c], fontsize=10)
        ax.set_xticks(range(1, 13), meses)
        ax.tick_params(labelsize=8)
        ax2.tick_params(labelsize=8, colors="#31688e")
    axes[0, 0].set_ylabel("focos armonizados (mediana)")
    fig.suptitle("Cusco 2003-2025: ciclo anual del fuego (barras) y del clima (línea), medianas por "
                 "mes · EXPLORATORIO", fontsize=11)
    fig.tight_layout()
    fig.savefig(RES / "perfil_estacional.png", dpi=130)
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    for ax, (c, base) in zip(axes, [("lluvia", "jul-oct"), ("vpd", "jul-oct"),
                                    ("humedad_suelo_15cm", "jul-oct")], strict=True):
        ax.scatter(anual[c], anual["focos"], color="#c2410c")
        for y, r in anual.iterrows():
            ax.annotate(str(y)[2:], (r[c], r["focos"]), fontsize=7, xytext=(2, 2),
                        textcoords="offset points")
        ax.set_xlabel(f"{ETIQUETA[c]} · media {base}", fontsize=9)
        ax.set_ylabel("focos armonizados jul-oct", fontsize=9)
        ax.tick_params(labelsize=8)
    fig.suptitle("Años (2003-2025): fuego de la temporada frente al clima de la temporada · "
                 "EXPLORATORIO", fontsize=11)
    fig.tight_layout()
    fig.savefig(RES / "anios_temporada.png", dpi=130)
    plt.close(fig)

    piv = corr.pivot_table(index="variable", columns="analisis", values="rho")
    cols = ["perfil estacional (12 meses)", "anomalía mensual, todos los meses",
            "anomalía mensual, jul-oct", "por punto, anomalía jul-oct (mediana de 8)",
            "años: clima jul-oct vs fuego jul-oct", "años: clima ene-jun vs fuego jul-oct"]
    piv = piv[cols].reindex(CORTOS)
    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(piv.values, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    cortas = ["ciclo anual\n(12 medianas)", "anomalía\ntodos los meses", "anomalía\njul-oct",
              "por punto\njul-oct", "años: clima\njul-oct", "años: clima\nene-jun previo"]
    ax.set_xticks(range(len(cols)), cortas, fontsize=8)
    ax.set_yticks(range(len(piv)), [ETIQUETA[c] for c in piv.index], fontsize=8)
    for i in range(piv.shape[0]):
        for j in range(piv.shape[1]):
            v = piv.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:+.2f}", ha="center", va="center", fontsize=8,
                        color="white" if abs(v) > 0.6 else "#1d2330")
    fig.colorbar(im, ax=ax, label="rho de Spearman")
    ax.set_title("Correlaciones exploratorias clima (Meteomatics) - focos armonizados, Cusco",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(RES / "correlaciones.png", dpi=130)
    plt.close(fig)


def informe(puntos: pd.DataFrame, corr: pd.DataFrame, estac: pd.DataFrame,
            anual: pd.DataFrame) -> None:
    def tabla_md(df: pd.DataFrame) -> str:
        cab = "| " + " | ".join(df.columns) + " |\n|" + "---|" * len(df.columns) + "\n"
        return cab + "\n".join("| " + " | ".join(str(v) for v in r) + " |"
                               for r in df.itertuples(index=False))

    def top(analisis: str, k: int = 5) -> pd.DataFrame:
        d = corr[corr["analisis"] == analisis].copy()
        d["abs"] = d["rho"].abs()
        d = d.sort_values("abs", ascending=False).head(k)
        return d.assign(variable=d["variable"].map(ETIQUETA))[["variable", "rho", "n"]]

    pts = puntos[["punto", "lat", "lon", "alt_m", "focos", "parte_del_fuego"]].copy()
    pts["parte_del_fuego"] = (pts["parte_del_fuego"] * 100).round(1).astype(str) + " %"
    texto = f"""# Clima (Meteomatics) y focos armonizados en Cusco: comparación exploratoria

*Generado por `exploratorio/meteomatics/explorar.py` · datos 2003-2025 · **exploratorio: no son
hallazgos ni pronósticos*** (MAESTRO §1.9 y `harmonizacion/sequia_fuego/PROTOCOLO.md`).

## Datos

- **Fuego:** focos armonizados de Cusco (`eq_hotspots`, MAESTRO v1.2), suma mensual, 2003-2025
  (276 meses, sin focos extrapolados).
- **Clima:** Meteomatics, un valor diario a las 18 UTC (13:00 local) en 8 puntos. Son los centros
  ponderados por fuego de las 8 celdas de 0.5° con más focos (juntas, el
  {puntos['parte_del_fuego'].sum():.0%} del fuego). El valor de Cusco es el promedio de los puntos
  ponderado por su parte del fuego. Lluvia y evapotranspiración se suman en el mes, las rachas se
  toman como máximo y el resto como media.

{tabla_md(pts)}

## Resultados (coeficiente de Spearman, rho)

Interpretación orientativa: |rho| < 0.3 débil, 0.3-0.5 moderado, > 0.5 fuerte. **Ninguno se usa
como prueba**: hay decenas de comparaciones sobre los mismos datos.

**1. Ciclo anual (12 medianas mensuales).** Es lo más claro, pero también lo más trivial: la
temporada seca coincide con la temporada de fuego.

{tabla_md(top("perfil estacional (12 meses)"))}

**2. Meses de la temporada (jul-oct), quitando el ciclo estacional.** ¿Un agosto más seco de lo
normal tiene más fuego de lo normal?

{tabla_md(top("anomalía mensual, jul-oct"))}

**3. Años: clima medio de jul-oct frente al total de focos de jul-oct (23 años).**

{tabla_md(top("años: clima jul-oct vs fuego jul-oct"))}

**4. Años: clima de ene-jun (temporada de lluvias previa) frente al fuego de jul-oct.**

{tabla_md(top("años: clima ene-jun vs fuego jul-oct"))}

**5. Rezagos: anomalía del clima de 1 a 3 meses antes frente al fuego de jul-oct.**

{tabla_md(top("rezago 1 mes(es), jul-oct", 3))}

{tabla_md(top("rezago 2 mes(es), jul-oct", 3))}

Tabla completa: `correlaciones.csv` · figuras: `perfil_estacional.png`, `anios_temporada.png`,
`correlaciones.png`.

## Límites

- **Exploratorio:** decenas de pruebas sobre los mismos 23 años. Un rho alto puede ser casualidad. Para
  confirmar algo, hay que fijar la hipótesis antes y probarla con datos nuevos (otras regiones o años),
  como pide el protocolo de `sequia_fuego/`.
- **Escala:** 8 puntos representan un departamento de ~72 000 km² con selva y puna; el fuego de
  cada punto se mide en su celda de 0.5° (~55 km).
- **Hora:** el VPD, la humedad del suelo y los índices son valores de las 13:00 local, no promedios
  diarios. Humedad relativa y viento medio no se pidieron (máximo 10 parámetros por consulta).
- **Fuente:** se desconoce el modelo o reanálisis de Meteomatics detrás de cada variable histórica;
  un cambio de modelo en la serie podría crear saltos.
- **Causalidad:** el clima puede favorecer el fuego, pero la mayoría de las quemas en Cusco son
  agrícolas o de pastos: dependen de decisiones humanas. Una correlación no lo distingue.
- **Licencia:** los datos de Meteomatics no se publican en el repositorio (solo coeficientes y
  figuras); la tabla mensual queda en `datos/` (ignorado por git).
"""
    (RES / "INFORME.md").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    main()
