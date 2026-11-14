"""CLI de FireCal (Typer).

Los comandos del pipeline se implementan fase por fase; por ahora solo ``serve`` funciona
y el resto informa en qué fase se implementará.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Annotated

import typer

from firecal.logging_utils import force_utf8_stdio, setup_logging
from firecal.settings import get_settings

# Antes de que Typer/rich imprima la ayuda: UTF-8 en la consola de Windows.
force_utf8_stdio()

app = typer.Typer(
    name="firecal",
    help="FireCal Perú: calendario de quemas armonizado MODIS/VIIRS (backend local).",
    no_args_is_help=True,
    add_completion=False,
)
log = logging.getLogger("firecal.cli")


class BuildStep(StrEnum):
    clean = "clean"
    aggregate = "aggregate"
    harmonize = "harmonize"
    all = "all"


class IngestSource(StrEnum):
    archive = "archive"
    nrt = "nrt"


class Mode(StrEnum):
    synthetic = "synthetic"
    real = "real"


@app.callback()
def _main() -> None:
    """Inicializa el logging con la configuración actual."""
    settings = get_settings()
    key = settings.env.firms_map_key
    setup_logging(settings.env.log_level, key.get_secret_value() if key else None)


def _not_implemented(command: str, phase: int) -> None:
    log.error("El comando '%s' todavia no esta implementado (Fase %d).", command, phase)
    raise typer.Exit(code=1)


@app.command()
def synth(
    scale: Annotated[float | None, typer.Option(help="Escala del número de eventos.")] = None,
    seed: Annotated[int | None, typer.Option(help="Semilla aleatoria.")] = None,
    start: Annotated[str | None, typer.Option(help="Fecha inicial YYYY-MM-DD.")] = None,
    end: Annotated[str | None, typer.Option(help="Fecha final YYYY-MM-DD (def.: hoy).")] = None,
) -> None:
    """Genera focos sintéticos con el formato de FIRMS en data/synthetic/."""
    from datetime import date

    from firecal.synth.generator import generate

    result = generate(
        get_settings(),
        scale=scale,
        seed=seed,
        start=date.fromisoformat(start) if start else None,
        end=date.fromisoformat(end) if end else None,
    )
    typer.echo(
        f"OK: {result.total_rows:,} filas en {len(result.rows_per_file)} archivos, "
        f"{result.n_events:,} eventos, {result.elapsed_s:.1f} s -> {result.out_dir}"
    )


@app.command()
def ingest(
    source: Annotated[
        IngestSource,
        typer.Option("--source", help="archive: CSV locales del modo actual; nrt: API FIRMS."),
    ] = IngestSource.archive,
) -> None:
    """Carga los CSV de FIRMS (o sintéticos) en DuckDB (tabla hotspots_raw)."""
    settings = get_settings()
    if source == IngestSource.nrt:
        from firecal.etl.nrt_fetch import PENDING_MESSAGE

        log.error(PENDING_MESSAGE)
        raise typer.Exit(code=1)

    from firecal.pipeline import run_ingest

    n = run_ingest(settings)
    typer.echo(f"OK: {n:,} focos normalizados en hotspots_raw (modo {settings.data_mode})")


@app.command()
def build(
    step: Annotated[
        BuildStep, typer.Option("--step", help="Paso del pipeline a ejecutar.")
    ] = BuildStep.all,
) -> None:
    """Ejecuta pasos del pipeline: limpieza, agregación y armonización."""
    from firecal import pipeline

    settings = get_settings()
    steps = list(BuildStep)[:-1] if step == BuildStep.all else [step]
    for st in steps:
        if st == BuildStep.clean:
            s = pipeline.run_clean(settings)
            typer.echo(f"OK clean: {s['n_input']:,} -> {s['n_output']:,} focos "
                       f"({s['n_static']:,} marcados como fuente fija)")
        elif st == BuildStep.aggregate:
            out = pipeline.run_aggregate(settings)
            typer.echo(f"OK aggregate: {out['n_rows']:,} filas en monthly_counts "
                       f"({out['n_focos']:,} focos, {out['n_cells']:,} celdas)")
        elif st == BuildStep.harmonize:
            out = pipeline.run_harmonize(settings)
            typer.echo(f"OK harmonize ({out['version']}): {out['n_rows']:,} filas; meses por "
                       f"fuente {out['months_by_source']}")


@app.command()
def validate() -> None:
    """Valida la armonización con años reservados y genera reportes."""
    from firecal.pipeline import run_validate

    m = run_validate(get_settings())
    acc = m["acceptance"]
    typer.echo(f"Sesgo regional SNPP->AQUA (reservados): {acc['value']:+.3f} "
               f"-> {'OK' if acc['passed'] else 'NO CUMPLE'} (|sesgo| < 0.15)")
    typer.echo("Reporte: reports/harmonization_metrics.json (+ graficos PNG)")


@app.command()
def train() -> None:
    """Entrena el modelo de perspectiva del mes siguiente."""
    _not_implemented("train", 7)


@app.command(name="plan-events")
def plan_events() -> None:
    """Carga los CSV armonizados de Cusco (MAESTRO.md) -> Parquet por anio/mes, con controles."""
    from firecal.plan.events import DataContractError, build_events

    try:
        meta = build_events(get_settings())
    except (DataContractError, FileNotFoundError) as exc:
        typer.echo(f"ERROR plan-events: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    c = meta["controles"]
    typer.echo(f"OK plan-events: Cusco {meta['primer_dia']}..{meta['ultimo_dia']} | "
               f"celda-dia {c['celda_dia']['filas']:,} filas, suma {c['celda_dia']['suma']:,.2f} | "
               f"focos {c['focos']['filas']:,} filas, suma {c['focos']['suma']:,.2f} | "
               "sumas de control de MAESTRO 6: OK (data/processed/plan/)")


@app.command()
def precompute() -> None:
    """Precalcula respuestas de la API por región para una demo instantánea."""
    from api.db import Repository
    from api.services.cache import precompute as run_precompute

    files = run_precompute(Repository(get_settings()))
    typer.echo(f"OK precompute: {len(files)} respuestas en data/processed/cache/")


@app.command()
def serve(
    host: Annotated[str | None, typer.Option(help="Host (por defecto FIRECAL_API_HOST).")] = None,
    port: Annotated[int | None, typer.Option(help="Puerto (por defecto FIRECAL_API_PORT).")] = None,
    reload: Annotated[bool, typer.Option(help="Recarga automática al cambiar código.")] = False,
) -> None:
    """Levanta la API FastAPI con uvicorn."""
    import uvicorn

    settings = get_settings()
    host = host or settings.env.api_host
    port = port or settings.env.api_port
    log.info("API en http://%s:%d (modo de datos: %s)", host, port, settings.data_mode)
    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


@app.command(name="all")
def run_all(
    mode: Annotated[Mode, typer.Option("--mode", help="Modo de datos.")] = Mode.synthetic,
) -> None:
    """Corre todo el pipeline: synth -> ingest -> build -> validate -> train -> precompute."""
    import time

    from firecal import pipeline

    settings = get_settings()
    if mode.value != settings.data_mode:
        log.error("--mode %s no coincide con FIRECAL_DATA_MODE=%s. Ajusta .env para no "
                  "etiquetar mal los datos.", mode.value, settings.data_mode)
        raise typer.Exit(code=1)
    t0 = time.perf_counter()
    if mode == Mode.synthetic:
        synth(scale=None, seed=None, start=None, end=None)
    n = pipeline.run_ingest(settings)
    typer.echo(f"OK ingest: {n:,} focos")
    build(step=BuildStep.all)
    validate()
    plan_events()
    log.warning("Paso 'train' pendiente (Fase 7); se omite.")
    precompute()
    typer.echo(f"OK all ({mode.value}) en {time.perf_counter() - t0:.0f} s. "
               "Siguiente: firecal serve")


if __name__ == "__main__":
    app()
