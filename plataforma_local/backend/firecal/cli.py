"""CLI de FireCal Cusco (Typer).

- ``firecal plan-events``: valida los CSV armonizados de Cusco (MAESTRO.md §6) y arma el Parquet.
- ``firecal serve``: levanta la API (y la interfaz compilada) con uvicorn.

El pipeline sintético anterior (synth, ingest, build, validate, precompute, all) se retiró el
14-nov-2026; está completo en la rama ``archivo/backend-sintetico``.
"""

from __future__ import annotations

import logging
from typing import Annotated

import typer

from firecal.logging_utils import force_utf8_stdio, setup_logging
from firecal.settings import get_settings

# Antes de que Typer/rich imprima la ayuda: UTF-8 en la consola de Windows.
force_utf8_stdio()

app = typer.Typer(
    name="firecal",
    help="FireCal Cusco: calendario armonizado de focos MODIS + VIIRS (datos de MAESTRO.md).",
    no_args_is_help=True,
    add_completion=False,
)
log = logging.getLogger("firecal.cli")


@app.callback()
def _main() -> None:
    """Inicializa el logging con la configuración actual."""
    settings = get_settings()
    key = settings.env.firms_map_key
    setup_logging(settings.env.log_level, key.get_secret_value() if key else None)


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
    log.info("API en http://%s:%d", host, port)
    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
