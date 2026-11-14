"""Banda ``band_p10`` / ``band_p90`` de una suma de celdas convertidas (AOI, celda padre, región).

1. Incertidumbre del FACTOR: para cada réplica b del bootstrap,
       total_b = sum_s R_s^b x V_s
   (V_s = focos VIIRS/Terra del AOI en el estrato s) y se toman los cuantiles ``band_quantiles``.
   Mide cuánto podría variar el factor, NO cuánto se equivoca la predicción de un mes concreto.
2. Error OBSERVADO (si la banda del factor cubre menos de ``band_min_coverage``): con
   e = log((obs + c) / (pred + c)) estimado por leave-one-year-out en ``calib_window`` (sin los
   años reservados) y agrupado por rangos del conteo PREDICHO, se ensancha la banda. Para un AOI
   se usa el conteo predicho del AOI completo:
       band_p10 = max(0, (factor_p10 + c) x exp(q_lo) - c)
       band_p90 =        (factor_p90 + c) x exp(q_hi) - c
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from firecal.settings import HarmonizationParams


def factor_band(
    groups: pd.DataFrame,
    group_cols: list[str],
    boot: dict[str, np.ndarray],
    quantiles: tuple[float, float],
) -> pd.DataFrame:
    """Cuantiles de sum_s R_s^b V_s por grupo. ``groups`` trae group_cols, estrato, raw_value."""
    if groups.empty:
        return pd.DataFrame(columns=[*group_cols, "factor_p10", "factor_p90"])
    estratos = sorted(groups["estrato"].unique())
    reps = np.vstack([boot[e] for e in estratos])            # (S, B)
    mat = groups.pivot_table(index=group_cols, columns="estrato", values="raw_value",
                             aggfunc="sum", fill_value=0.0).reindex(columns=estratos,
                                                                     fill_value=0.0)
    totals = mat.to_numpy() @ reps                             # (G, B)
    q = np.quantile(totals, quantiles, axis=1)
    out = mat.index.to_frame(index=False)
    out["factor_p10"], out["factor_p90"] = q[0], q[1]
    return out


def fit_error_model(obs: np.ndarray, pred: np.ndarray, hp: HarmonizationParams) -> pd.DataFrame:
    """Cuantiles empíricos de e = log((obs + c) / (pred + c)) por rangos del conteo predicho.

    Rangos: ``band_error_pred_edges`` (el último va hasta infinito). Un rango con menos de
    ``band_error_min_n`` unidades se fusiona con el rango inferior (o el superior si es el primero).
    """
    c = hp.band_log_offset
    obs, pred = np.asarray(obs, float), np.asarray(pred, float)
    err = np.log((obs + c) / (pred + c))
    edges = list(hp.band_error_pred_edges)

    def counts(e: list[float]) -> np.ndarray:
        idx = np.searchsorted(np.asarray(e), pred, side="right") - 1
        return np.bincount(np.clip(idx, 0, len(e) - 1), minlength=len(e))

    n = counts(edges)
    while len(edges) > 1 and n.min() < hp.band_error_min_n:
        i = int(np.argmin(n))
        del edges[i if i > 0 else 1]  # fusiona el rango i con el inferior (o el 0 con el 1)
        n = counts(edges)
    idx = np.clip(np.searchsorted(np.asarray(edges), pred, side="right") - 1, 0, len(edges) - 1)
    rows = []
    for b, lo in enumerate(edges):
        e = err[idx == b]
        if e.size == 0:
            continue
        q_lo, q_hi = np.quantile(e, hp.band_quantiles)
        hi = edges[b + 1] if b + 1 < len(edges) else float("inf")
        rows.append({"bin": b, "pred_lo": float(lo), "pred_hi": float(hi),
                     "q_lo": float(min(q_lo, 0.0)), "q_hi": float(max(q_hi, 0.0)),
                     "n": int(e.size)})
    return pd.DataFrame(rows)


def widen(value: np.ndarray, f_lo: np.ndarray, f_hi: np.ndarray, model: pd.DataFrame | None,
          hp: HarmonizationParams) -> tuple[np.ndarray, np.ndarray]:
    """Aplica el modelo de error a la banda del factor (si ``model`` es None, no cambia)."""
    f_lo, f_hi = np.asarray(f_lo, float), np.asarray(f_hi, float)
    if model is None or model.empty:
        return f_lo, f_hi
    c = hp.band_log_offset
    edges = model["pred_lo"].to_numpy()
    idx = np.clip(np.searchsorted(edges, np.asarray(value, float), side="right") - 1, 0,
                  len(model) - 1)
    q_lo, q_hi = model["q_lo"].to_numpy()[idx], model["q_hi"].to_numpy()[idx]
    lo = np.maximum(0.0, (f_lo + c) * np.exp(q_lo) - c)
    hi = (f_hi + c) * np.exp(q_hi) - c
    return lo, hi


def coverage(obs: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    obs = np.asarray(obs, float)
    return float(np.mean((obs >= lo) & (obs <= hi))) if obs.size else float("nan")
