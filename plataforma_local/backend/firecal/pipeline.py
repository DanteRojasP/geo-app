"""Pasos del pipeline invocados por la CLI. Idénticos en modo sintético y real."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from firecal.etl.aggregate import (
    assign_h3,
    build_cells_table,
    build_monthly_counts,
    build_regions_table,
)
from firecal.etl.archive_loader import load_archive
from firecal.etl.clean import clean_hotspots
from firecal.etl.load import HOTSPOT_TYPES, connect, read_table, set_info, write_table
from firecal.regions import get_region, load_regions
from firecal.settings import Settings

log = logging.getLogger(__name__)

RAW_TABLE = "hotspots_raw"
HOTSPOTS_TABLE = "hotspots"
CLEAN_VIEW = "hotspots_clean"  # hotspots sin fuentes fijas: lo que usa todo cálculo posterior


def run_ingest(settings: Settings) -> int:
    """Lee los CSV de la carpeta de entrada del modo actual -> tabla ``hotspots_raw``."""
    df = load_archive(settings)
    with connect(settings.paths.duckdb_path) as con:
        write_table(con, RAW_TABLE, df, HOTSPOT_TYPES)
        # El modo queda grabado con los datos: la API etiqueta según el origen real.
        set_info(con, data_mode=settings.data_mode, input_dir=settings.input_dir.name,
                 ingested_at=_now())
    return len(df)


def run_clean(settings: Settings) -> dict:
    """``hotspots_raw`` -> limpieza -> tabla ``hotspots`` + vista ``hotspots_clean``."""
    region = get_region(settings)
    with connect(settings.paths.duckdb_path) as con:
        _require_tables(con, RAW_TABLE)
        raw = read_table(con, RAW_TABLE)
        clean, report = clean_hotspots(raw, region.geometry, settings.params)
        clean["h3_7"] = None  # se asigna en la Fase 3 (agregación)
        clean = clean[[c for c in HOTSPOT_TYPES if c in clean.columns]]
        write_table(con, HOTSPOTS_TABLE, clean, HOTSPOT_TYPES)
        con.execute(f'CREATE OR REPLACE VIEW "{CLEAN_VIEW}" AS '
                    f'SELECT * FROM "{HOTSPOTS_TABLE}" WHERE NOT is_static')

    summary = {
        "data_mode": settings.data_mode,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "region": region.code,
        **report.to_dict(),
    }
    out = settings.paths.reports_dir / "clean_summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")
    return summary


def _require_tables(con, *names: str) -> None:
    tables = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables")
              .fetchall()}
    missing = [n for n in names if n not in tables]
    if missing:
        raise RuntimeError(f"Faltan tablas {missing}. Ejecuta los pasos anteriores del pipeline.")


def run_aggregate(settings: Settings) -> dict:
    """``hotspots`` -> h3_7, ``regions``, ``cells``, ``monthly_counts``, ``satellite_coverage``."""
    g = settings.params.grid
    regions = load_regions(settings.paths.regions_dir)
    with connect(settings.paths.duckdb_path) as con:
        _require_tables(con, HOTSPOTS_TABLE)
        assign_h3(con, g.h3_res_store)
        build_regions_table(con, regions)
        n_cells = build_cells_table(con, regions, g.h3_res_store, g.h3_res_calibration_parent)
        n_rows = build_monthly_counts(con)
        n_focos = con.execute("SELECT sum(n_focos) FROM monthly_counts").fetchall()[0][0]
        n_clean = con.execute(f'SELECT count(*) FROM "{CLEAN_VIEW}"').fetchall()[0][0]
    if n_focos != n_clean:
        raise RuntimeError(f"monthly_counts suma {n_focos} focos pero hay {n_clean} limpios")
    return {"n_cells": n_cells, "n_rows": n_rows, "n_focos": int(n_focos)}


# --------------------------------------------------------------------------------------
# Fase 4: armonización
# --------------------------------------------------------------------------------------
# Par de producción -> cadena de validación cuyo error observado se usa para su banda.
# N21 no tiene solape con Aqua: usa el error de la cadena N20 (documentado en METODOLOGIA.md).
ERROR_MODEL_SOURCE = {"SNPP->AQUA": "SNPP->AQUA", "N20->AQUA": "N20->SNPP->AQUA",
                      "N21->AQUA": "N20->SNPP->AQUA", "TERRA->AQUA": "TERRA->AQUA"}
APPLIED_PAIRS = tuple(ERROR_MODEL_SOURCE)


def run_harmonize(settings: Settings) -> dict:
    """monthly_counts (D) -> calibración + validación -> harmonized_monthly y tablas de params."""
    import pandas as pd

    from firecal.harmonization.apply import assemble, fit_calibrations, month_plan
    from firecal.harmonization.calibrate import bootstrap_table, params_table
    from firecal.harmonization.data import load_day_counts
    from firecal.harmonization.validate import holdout_validation

    hp = settings.params.harmonization
    with connect(settings.paths.duckdb_path) as con:
        _require_tables(con, "monthly_counts", "cells")
        dc = load_day_counts(con, hp)
        cals = fit_calibrations(dc, hp)
        validations = holdout_validation(dc, hp)
        plan = month_plan(dc, cals, hp)
        harmonized = assemble(dc, cals, plan, hp.data_version)

        params = pd.concat([params_table(c, hp.data_version) for c in cals.cals.values()],
                           ignore_index=True)
        boot = pd.concat([bootstrap_table(cals[p]) for p in APPLIED_PAIRS if p in cals],
                         ignore_index=True)
        err_rows = []
        for pair in APPLIED_PAIRS:
            chain = ERROR_MODEL_SOURCE[pair]
            if pair not in cals or chain not in validations:
                continue
            v = validations[chain]
            applied = v["report"]["band"]["widened_with_observed_error"]
            err_rows.append(v["error_model"].assign(pair=pair, source_chain=chain,
                                                    applied=applied))
        band_error = pd.concat(err_rows, ignore_index=True) if err_rows else pd.DataFrame()

        write_table(con, "harmonization_params", params)
        write_table(con, "harmonization_bootstrap", boot)
        write_table(con, "harmonization_band_error", band_error)
        write_table(con, "harmonized_months", plan)
        write_table(con, "harmonized_monthly", harmonized)
        set_info(con, harmonized_at=_now(), data_version=hp.data_version)
    return {"n_rows": len(harmonized), "months_by_source": plan.groupby("source").size().to_dict(),
            "pairs": sorted(cals.cals), "version": hp.data_version}


def run_validate(settings: Settings) -> dict:
    """Reporte de validación: reports/harmonization_metrics.json + gráficos PNG."""
    import pandas as pd

    from firecal.harmonization.apply import fit_calibrations
    from firecal.harmonization.data import load_day_counts
    from firecal.harmonization.validate import (
        aqua_snpp_ratio_by_year,
        contrast_regression,
        holdout_validation,
        make_plots,
        reliability_curve,
        synthetic_truth_check,
    )

    hp = settings.params.harmonization
    with connect(settings.paths.duckdb_path, read_only=True) as con:
        _require_tables(con, "harmonized_monthly", "harmonized_months")
        dc = load_day_counts(con, hp)
        harmonized = read_table(con, "harmonized_monthly")
        plan = read_table(con, "harmonized_months")
        params = read_table(con, "harmonization_params")
    cals = fit_calibrations(dc, hp)
    validations = holdout_validation(dc, hp)
    ratio_year = aqua_snpp_ratio_by_year(dc, hp)

    snpp = validations.get("SNPP->AQUA", {}).get("report", {})
    bias = (snpp.get("regional") or {}).get("bias_rel")
    metrics = {
        "data_mode": settings.data_mode,
        "version": hp.data_version,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "unit": "focos equivalentes a MODIS-Aqua DIURNO (las detecciones nocturnas no entran)",
        "method": "razon de sumas por estrato (celda padre H3 res 4 x temporada, fusion a res 3 "
                  "y regional), bootstrap por bloques de anios",
        "acceptance": {"criterion": "|sesgo relativo regional| < 0.15 en anios reservados "
                                    "(SNPP->AQUA)",
                       "value": bias, "passed": bias is not None and abs(bias) < 0.15},
        "chains": {k: v["report"] for k, v in validations.items()},
        "contrast_snpp_aqua": contrast_regression(dc, hp),
        "production_strata": {p: g["level"].value_counts().to_dict()
                              for p, g in params.groupby("pair")},
        "production_regional_ratios": {
            f"{r.pair}|{r.season}": {"ratio": r.ratio, "p10": r.p10, "p90": r.p90}
            for r in params[params["level"].isin(["region", "region*region"])].itertuples()},
        "months_by_source": plan.groupby("source").size().to_dict(),
        "reliability_curve": {
            "description": "Error relativo mensual (anios reservados, SNPP->AQUA) por celda padre "
                           "res 4 segun su conteo anual esperado. Base de los umbrales de "
                           "reliability en settings.yaml.",
            "thresholds": settings.params.reliability.model_dump(exclude={"report_edges"}),
            "curve": reliability_curve(validations["SNPP->AQUA"]["validation"], dc, hp,
                                       settings.params.reliability.report_edges)
            if "SNPP->AQUA" in validations else [],
        },
        "aqua_snpp_ratio_by_year": ratio_year,
        "aqua_snpp_ratio_by_year_note": (
            "Solo informativo en modo sintetico (la deriva la simula el generador)."
            if settings.data_mode == "synthetic" else "Usar para revisar aqua_observed_until."),
    }
    if settings.data_mode == "synthetic":
        truth_path = settings.paths.synthetic_dir / "truth.parquet"
        if truth_path.is_file():
            metrics["synthetic_truth_check"] = synthetic_truth_check(
                dc, harmonized, plan, pd.read_parquet(truth_path), hp)
    metrics["plots"] = make_plots(settings.paths.reports_dir, dc, harmonized, plan, cals,
                                  validations, ratio_year)
    out = settings.paths.reports_dir / "harmonization_metrics.json"
    out.write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=_json_default)
                   + "\n", encoding="utf-8", newline="\n")
    return metrics


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _json_default(obj):
    """numpy -> tipos nativos para json."""
    import numpy as np

    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f"No serializable: {type(obj)}")
