"""Analíticas sencillas sobre la serie armonizada de Cusco (``PlanStore``).

Cinco cálculos de sumas y percentiles, pensados para un gestor que no es especialista. Cada
resultado trae ``en_simple`` (una frase que se entiende sin gráfico) y ``como_leerlo`` (cómo
interpretar los números), además de los datos para dibujar.

- ``estacionalidad``: en qué meses se concentra el fuego.
- ``ranking``: qué años tuvieron más y menos fuego.
- ``acumulado``: cómo fue avanzando un año frente a lo normal.
- ``altitud``: a qué altitud ocurre el fuego.
- ``recurrencia``: qué lugares arden año tras año.

Límites (MAESTRO.md): se describen focos armonizados, no incendios ni área quemada; nada de
esto es un pronóstico. La historia de referencia son los años completos sin focos
extrapolados (2003 en adelante).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from firecal.plan.query import AOI, NOTE_2025, UNIDAD, PlanError, PlanNoData, PlanStore

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
# Parte del total anual que define la "temporada de fuego".
PARTE_TEMPORADA = 0.80
# La recurrencia se mide solo con VIIRS (desde 2013): MODIS localiza peor y marca menos celdas.
RECURRENCIA_DESDE = 2013
BANDAS_ALTITUD = [(None, 1500, "menos de 1,500 m"), (1500, 2500, "1,500 a 2,500 m"),
                  (2500, 3500, "2,500 a 3,500 m"), (3500, None, "más de 3,500 m")]
SIN_DATOS = "Sin datos: no hay focos armonizados en {label}."
NOTA_NO_ES_PRONOSTICO = ("Describe lo que ya ocurrió según los satélites. No es un pronóstico "
                         "ni mide incendios o área quemada.")


def _n(x: float) -> str:
    """Número para una frase: entero con separador de miles."""
    return f"{round(float(x)):,}"


def _pct(x: float) -> str:
    return f"{round(100 * float(x))} %"


def _veces(valor: float, base: float) -> str:
    """Comparación en palabras: 'casi el doble de', '30 % más que', 'parecido a'..."""
    if base <= 0:
        return "muy por encima de"
    r = valor / base
    if r >= 2.75:
        return f"unas {round(r)} veces"
    if r >= 1.85:
        return "cerca del doble de" if r < 2.25 else "más del doble de"
    if r >= 1.15:
        return f"{round(100 * (r - 1))} % más que"
    if r > 0.85:
        return "parecido a"
    return f"{round(100 * (1 - r))} % menos que"


def _lista(nombres: list[str]) -> str:
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def _envoltura(aoi: AOI, titulo: str, en_simple: str, como_leerlo: str, cuerpo: dict,
               notes: list[str] | None = None) -> dict:
    return {"aoi": aoi.info(), "titulo": titulo, "en_simple": en_simple,
            "como_leerlo": como_leerlo, "unidad": UNIDAD, **cuerpo,
            "notes": [NOTA_NO_ES_PRONOSTICO, *(notes or [])]}


def _mensual(store: PlanStore, aoi: AOI) -> pd.DataFrame:
    full = store.monthly(aoi).rename(columns={"focos_armonizados": "n"})
    if full["n"].sum() == 0:
        raise PlanNoData(SIN_DATOS.format(label=aoi.label))
    return full


def _fuente(aoi: AOI) -> tuple[str, str, str, list]:
    """(tabla, columna de peso, condición WHERE, parámetros) según el AOI.

    Igual que ``PlanStore._monthly``: Cusco entero suma ``eq_hotspots`` de la tabla de celda-día;
    un área dibujada suma ``eq_foco`` de los focos que caen dentro.
    """
    if aoi.whole_region:
        return "cd", "eq_hotspots", "TRUE", []
    return "fo", "eq_foco", f"({aoi.sql}) AND en_serie = 1", list(aoi.params)


def _anios_referencia(full: pd.DataFrame) -> list[int]:
    """Años con sus 12 meses y sin focos extrapolados: la historia con la que se compara."""
    ok = full.assign(limpio=full["calidad"].isin(["referencia", "calibrado"])
                     & ~full["parcial"])
    g = ok.groupby("anio").agg(meses=("mes", "size"), limpio=("limpio", "all"))
    return sorted(int(a) for a in g.index[(g["meses"] == 12) & g["limpio"]])


# ------------------------------------------------------------------ 1. estacionalidad
def estacionalidad(store: PlanStore, aoi: AOI) -> dict:
    full = _mensual(store, aoi)
    ref = _anios_referencia(full)
    hist = full[full["anio"].isin(ref)]
    total = float(hist["n"].sum())
    por_mes = hist.groupby("mes")["n"]
    tabla = pd.DataFrame({"mediana": por_mes.median(), "p25": por_mes.quantile(0.25),
                          "p75": por_mes.quantile(0.75), "parte": por_mes.sum() / total})
    # Temporada: los meses de mayor actividad que juntos suman el 80 % del año.
    orden = tabla["parte"].sort_values(ascending=False)
    temporada = sorted(int(m) for m in orden.index[: int((orden.cumsum() < PARTE_TEMPORADA).sum())
                                                   + 1])
    parte_temporada = float(tabla.loc[temporada, "parte"].sum())
    pico = int(tabla["mediana"].idxmax())        # el mes más activo en un año típico
    seguidos = temporada == list(range(temporada[0], temporada[-1] + 1))
    cuando = (f"va de {MESES[temporada[0] - 1]} a {MESES[temporada[-1] - 1]}"
              if seguidos and len(temporada) > 1
              else f"se concentra en {_lista([MESES[m - 1] for m in temporada])}")
    en_simple = (f"La temporada de fuego {cuando}: esos meses reúnen el {_pct(parte_temporada)} "
                 f"del fuego del año. El mes más activo es {MESES[pico - 1]}, con unos "
                 f"{_n(tabla.loc[pico, 'mediana'])} focos armonizados en un año típico.")
    return _envoltura(
        aoi, "¿Cuándo hay más fuego?", en_simple,
        "Cada barra es un mes. La altura es lo habitual (mediana) y el rango marca entre qué "
        "valores cae la mitad de los años.",
        {"anios_referencia": [ref[0], ref[-1]], "temporada": temporada, "mes_pico": pico,
         "parte_temporada": round(parte_temporada, 3),
         "meses": [{"mes": int(m), "nombre": MESES[m - 1], "mediana": round(float(r.mediana), 1),
                    "p25": round(float(r.p25), 1), "p75": round(float(r.p75), 1),
                    "parte_del_anio": round(float(r.parte), 3), "en_temporada": m in temporada}
                   for m, r in tabla.iterrows()]})


# ------------------------------------------------------------------ 2. ranking de años
def ranking(store: PlanStore, aoi: AOI) -> dict:
    full = _mensual(store, aoi)
    ref = _anios_referencia(full)
    completos = full.groupby("anio").filter(lambda g: len(g) == 12)
    ext = completos["n"] * completos["fraccion_extrapolada"]
    anual = completos.assign(ext=ext).groupby("anio").agg(
        total=("n", "sum"), ext=("ext", "sum"), incertidumbre=("incertidumbre", "sum"))
    tipico = float(anual.loc[ref, "total"].median())
    anual = anual.sort_values("total", ascending=False)
    filas = []
    for puesto, (anio, r) in enumerate(anual.iterrows(), start=1):
        frac = float(r.ext / r.total) if r.total > 0 else 0.0
        filas.append({"puesto": puesto, "anio": int(anio), "total": round(float(r.total), 1),
                      "respecto_al_tipico": round(float(r.total) / tipico, 2) if tipico else None,
                      "calidad": "extrapolado" if frac > 0.5 else "mixto" if frac > 0 else "ok",
                      "incertidumbre": round(float(r.incertidumbre), 1)})
    firmes = [f for f in filas if f["calidad"] == "ok"]
    mayor, menor = firmes[0], firmes[-1]
    en_simple = (f"El año con más fuego fue {mayor['anio']}, con {_n(mayor['total'])} focos "
                 f"armonizados: {_veces(mayor['total'], tipico)} un año típico "
                 f"({_n(tipico)}). El más tranquilo fue {menor['anio']}, con "
                 f"{_n(menor['total'])}.")
    notes = []
    if any(f["calidad"] != "ok" for f in filas):
        notes.append("Los años con focos extrapolados (antes de julio de 2002) aparecen en la "
                     "lista con su margen, pero no se usan para el año típico ni para el primer "
                     "y último puesto de la frase.")
    if any(f["anio"] == 2025 for f in filas):
        notes.append(NOTE_2025)
    return _envoltura(
        aoi, "¿Qué años tuvieron más fuego?", en_simple,
        "Cada barra es un año. La línea punteada marca un año típico: las barras que la superan "
        "tuvieron más fuego de lo habitual. Las barras claras incluyen focos extrapolados.",
        {"anio_tipico": round(tipico, 1), "anios_referencia": [ref[0], ref[-1]], "anios": filas},
        notes)


# ------------------------------------------------------------------ 3. curva acumulada
def _diario(store: PlanStore, aoi: AOI) -> pd.DataFrame:
    tabla, peso, where, params = _fuente(aoi)
    cur = store.cursor()
    df = cur.execute(
        f"SELECT anio, dayofyear(CAST(fecha_local AS DATE)) AS dia, sum({peso}) AS n "
        f"FROM {tabla} WHERE {where} GROUP BY 1, 2", params).df()
    cur.close()
    df["dia"] = df["dia"].clip(upper=365)          # el 31-dic de un bisiesto cuenta como día 365
    dias = df.pivot_table(index="anio", columns="dia", values="n", aggfunc="sum", fill_value=0.0)
    return dias.reindex(columns=range(1, 366), fill_value=0.0).cumsum(axis=1)


def acumulado(store: PlanStore, aoi: AOI, anio: int | None) -> dict:
    full = _mensual(store, aoi)
    ref = _anios_referencia(full)
    completos = sorted(int(a) for a, g in full.groupby("anio") if len(g) == 12)
    anio = completos[-1] if anio is None else int(anio)
    if anio not in completos:
        raise PlanError(f"Año {anio} no disponible: elige uno entre {completos[0]} y "
                        f"{completos[-1]}.")
    curvas = _diario(store, aoi).reindex(completos, fill_value=0.0)
    # Misma historia de referencia que el ranking, para que 'un año típico' sea un solo número.
    base = curvas.loc[ref]
    mediana, p10, p90 = (base.quantile(q) for q in (0.5, 0.1, 0.9))
    curva = curvas.loc[anio]
    final, normal, bajo, alto = (float(s.iloc[-1]) for s in (curva, mediana, p10, p90))
    if final > alto:
        veredicto = "muy por encima de lo normal"
    elif final < bajo:
        veredicto = "muy por debajo de lo normal"
    else:
        veredicto = "dentro de lo normal"
    en_simple = (f"{anio} cerró con {_n(final)} focos armonizados, {veredicto}: un año típico "
                 f"cierra con {_n(normal)} (entre {_n(bajo)} y {_n(alto)}).")
    cruce = np.flatnonzero(curva.to_numpy() >= normal)
    if final > normal and len(cruce) and cruce[0] < 364:
        # Fecha real del año consultado: con 2001 fijo, en los bisiestos salía un día después
        # (2020 cruzó el 24 de agosto, no el 25).
        fecha = pd.Timestamp(anio, 1, 1) + pd.Timedelta(days=int(cruce[0]))
        en_simple += (f" El {fecha.day} de {MESES[fecha.month - 1]} ya había alcanzado lo que "
                      "un año típico suma en doce meses.")
    dias = sorted({*range(7, 366, 7), 365})
    notes = []
    if anio not in ref:
        notes.append(f"{anio} tiene focos extrapolados: su curva es una referencia gruesa.")
    if anio == 2025:
        notes.append(NOTE_2025)                 # MAESTRO P2: el 2025 bajo lleva su nota
    return _envoltura(
        aoi, f"¿Cómo avanzó {anio} frente a lo normal?", en_simple,
        "La línea del año va sumando focos día a día. La banda es donde cae la mayoría de los "
        "años (8 de cada 10) y la línea central es lo habitual. Si el año sube por encima de la "
        "banda, fue excepcional.",
        {"anio": anio, "anios_referencia": [ref[0], ref[-1]], "veredicto": veredicto,
         "total": round(final, 1), "normal": round(normal, 1),
         "rango_normal": [round(bajo, 1), round(alto, 1)],
         "curva": [{"dia": d, "acumulado": round(float(curva[d]), 1),
                    "normal": round(float(mediana[d]), 1), "bajo": round(float(p10[d]), 1),
                    "alto": round(float(p90[d]), 1)} for d in dias]},
        notes)


# ------------------------------------------------------------------ 4. altitud
def altitud(store: PlanStore, aoi: AOI) -> dict:
    _mensual(store, aoi)
    casos = " ".join(
        f"WHEN alt_m {'<' if hi is not None else '>='} {hi if hi is not None else lo} THEN {i}"
        for i, (lo, hi, _) in enumerate(BANDAS_ALTITUD) if i < len(BANDAS_ALTITUD) - 1)
    tabla, peso, where, params = _fuente(aoi)
    cur = store.cursor()
    df = cur.execute(
        f"SELECT CASE WHEN alt_m IS NULL THEN -1 {casos} ELSE {len(BANDAS_ALTITUD) - 1} END "
        f"AS banda, sum({peso}) AS n, count(DISTINCT (cell_lat, cell_lon)) AS celdas "
        f"FROM {tabla} WHERE {where} GROUP BY 1", params).df()
    cur.close()
    total = float(df["n"].sum())
    por = df.set_index("banda")
    bandas = []
    for i, (lo, hi, nombre) in enumerate(BANDAS_ALTITUD):
        n = float(por["n"].get(i, 0.0))
        bandas.append({"banda": nombre, "desde_m": lo, "hasta_m": hi,
                       "focos_armonizados": round(n, 1), "parte": round(n / total, 3),
                       "celdas": int(por["celdas"].get(i, 0))})
    mayor = max(bandas, key=lambda b: b["parte"])
    alto = sum(b["parte"] for b in bandas if (b["desde_m"] or 0) >= 2500)
    en_simple = (f"La franja con más fuego es la de {mayor['banda']}: reúne el "
                 f"{_pct(mayor['parte'])} de los focos armonizados. En total, el "
                 f"{_pct(alto)} ocurre sobre los 2,500 m y el {_pct(1 - alto)} por debajo.")
    notes = []
    if -1 in por.index:
        notes.append(f"{_n(por['n'][-1])} focos armonizados no tienen altitud y no entran en "
                     "las franjas.")
    return _envoltura(
        aoi, "¿A qué altitud ocurre el fuego?", en_simple,
        "Cada franja muestra qué parte de todo el fuego del periodo ocurrió a esa altitud.",
        {"bandas": bandas}, notes)


# ------------------------------------------------------------------ 5. recurrencia
def recurrencia(store: PlanStore, aoi: AOI, limite: int = 5000) -> dict:
    _mensual(store, aoi)
    tabla, peso, where, params = _fuente(aoi)
    cur = store.cursor()
    df = cur.execute(
        f"SELECT cell_lat AS lat, cell_lon AS lon, count(DISTINCT anio) AS anios, "
        f"sum({peso}) AS n, max(anio) AS ultimo FROM {tabla} "
        f"WHERE {where} AND anio >= {RECURRENCIA_DESDE} GROUP BY 1, 2", params).df()
    ultimo_anio = cur.execute("SELECT max(anio) FROM cd").fetchall()[0][0]
    cur.close()
    if df.empty:
        raise PlanNoData(SIN_DATOS.format(label=f"{aoi.label} desde {RECURRENCIA_DESDE}"))
    posibles = int(ultimo_anio) - RECURRENCIA_DESDE + 1
    total = len(df)
    una_vez = int((df["anios"] == 1).sum())
    umbral = max(3, round(posibles / 3))            # "recurrente": arde 1 de cada 3 años o más
    frecuentes = int((df["anios"] >= umbral).sum())
    tope = int(df["anios"].max())
    df = df.sort_values(["anios", "n"], ascending=False)
    en_simple = (f"Desde {RECURRENCIA_DESDE} se detectó fuego en {_n(total)} lugares de ~1 km. "
                 f"En el {_pct(una_vez / total)} de ellos ardió un solo año; {_n(frecuentes)} "
                 f"lugares ardieron en {umbral} o más de los {posibles} años, y el más "
                 f"repetido lo hizo en {tope}.")
    return _envoltura(
        aoi, "¿Dónde vuelve a arder?", en_simple,
        "Cada punto es una celda de ~1 km. El número es en cuántos años distintos tuvo fuego: "
        "cuanto más alto, más se repite en ese lugar.",
        {"desde": RECURRENCIA_DESDE, "anios_posibles": posibles, "lugares": total,
         "umbral_recurrente": umbral, "lugares_recurrentes": frecuentes,
         "por_numero_de_anios": [{"anios": int(k), "lugares": int(v)} for k, v in
                                 df["anios"].value_counts().sort_index().items()],
         "celdas_devueltas": min(total, limite),
         "celdas": [{"lat": round(float(r.lat), 3), "lon": round(float(r.lon), 3),
                     "anios": int(r.anios), "ultimo_anio": int(r.ultimo)}
                    for r in df.head(limite).itertuples(index=False)]},
        ["Solo se usa VIIRS (desde 2013) para que todos los años se vean con el mismo detalle."])


# ------------------------------------------------------------------ resumen
def resumen(store: PlanStore, aoi: AOI) -> dict:
    """Las cinco frases juntas: la respuesta corta para quien no va a mirar gráficos."""
    partes = [estacionalidad(store, aoi), ranking(store, aoi), acumulado(store, aoi, None),
              altitud(store, aoi), recurrencia(store, aoi, limite=0)]
    notes = [NOTA_NO_ES_PRONOSTICO]
    if partes[2]["anio"] == 2025:               # la frase de la curva habla de 2025
        notes.append(NOTE_2025)
    return {"aoi": aoi.info(), "titulo": f"El fuego en {aoi.label}, en simple",
            "unidad": UNIDAD,
            "frases": [{"pregunta": p["titulo"], "respuesta": p["en_simple"]} for p in partes],
            "notes": notes}
