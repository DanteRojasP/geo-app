"""Aplicación FastAPI de FireCal: CORS, salud, routers v1 y manejo de errores."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from api.db import Repository
from api.limits import HeavyGate, RateLimiter
from api.routers import anomaly, calendar, forecast, hotspots, map, meta, plan, regions
from api.schemas import HealthResponse
from api.services.common import AOIError
from firecal import __version__
from firecal.plan.query import PlanStore
from firecal.settings import PROJECT_ROOT, Settings, get_settings

API_PREFIX = "/api/v1"
# Frontend estático (Leaflet). FIRECAL_FRONTEND_DIR lo cambia (p. ej. en Docker); vacío = no servir.
DEFAULT_FRONTEND = PROJECT_ROOT.parent / "frontend"


class UTF8JSONResponse(JSONResponse):
    """JSON con charset explícito (PowerShell 5.1 asume Latin-1 si no se declara)."""

    media_type = "application/json; charset=utf-8"


def create_app(settings: Settings | None = None) -> FastAPI:
    """Crea la app. Recibe ``settings`` explícitos en tests; si no, usa los globales."""
    settings = settings or get_settings()

    app = FastAPI(
        default_response_class=UTF8JSONResponse,
        title="FireCal Perú API",
        version=__version__,
        description=(
            "Calendario armonizado de focos de calor MODIS + VIIRS para **Cusco** (2000-11 a "
            "2025-12), con datos reales de NASA FIRMS. Unidad: **focos armonizados** (celdas de "
            "~1 km con fuego por día, en escala MODIS). Detalles en `GET /api/metadatos`."
        ),
    )
    app.state.settings = settings
    app.state.repo = Repository(settings)
    app.state.plan = PlanStore(settings)
    rl = settings.params.api.rate_limit
    app.state.limiter = RateLimiter(rl)
    app.state.gate = HeavyGate(rl.max_concurrent_heavy, rl.queue_timeout_s)

    @app.middleware("http")
    async def _timing_and_limits(request: Request, call_next):
        """Protocolo de solicitudes (429 por cliente) y latencia en X-Process-Time-ms."""
        t0 = time.perf_counter()
        rejected = app.state.limiter.check(request)
        response = rejected or await call_next(request)
        response.headers["X-Process-Time-ms"] = f"{(time.perf_counter() - t0) * 1000:.1f}"
        remaining = getattr(request.state, "rate_remaining", None)
        if remaining is not None:
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.params.api.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Data-Mode", "X-Row-Count",
                        "X-Process-Time-ms", "X-RateLimit-Remaining", "Retry-After"],
    )

    @app.exception_handler(AOIError)
    def _aoi_error(_: Request, exc: AOIError) -> JSONResponse:
        return UTF8JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"campo": ".".join(str(x) for x in e.get("loc", [])[1:]),
                   "error": e.get("msg", "")} for e in exc.errors()]
        return UTF8JSONResponse(status_code=422, content={
            "detail": "Solicitud inválida: revisa los campos indicados en 'errors'.",
            "errors": errors})

    legacy = settings.params.api.legacy_v1

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        """Estado del servicio: si los datos de Cusco están cargados (o la base sintética, en
        modo legacy_v1)."""
        if legacy:
            repo: Repository = app.state.repo
            ready = repo.ready
            mode = repo.data_mode if ready else settings.data_mode
            return HealthResponse(status="ok", data_mode=mode, data_ready=ready)
        plan_store: PlanStore = app.state.plan
        return HealthResponse(status="ok", data_mode="real", data_ready=plan_store.ready)

    @app.get("/health/limits", tags=["meta"])
    def health_limits() -> dict:
        """Estado del protocolo de solicitudes: clientes, rechazos 429/503 y pesadas en curso."""
        return {**app.state.limiter.stats(), **app.state.gate.stats()}

    # Backend anterior (alternativa B, datos SINTÉTICOS de 5 departamentos): apagado por defecto
    # porque el prototipo usa solo los datos reales de Cusco (MAESTRO §12).
    if legacy:
        for module in (regions, calendar, anomaly, hotspots, map, forecast, meta):
            app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(plan.router)

    frontend = Path(os.environ.get("FIRECAL_FRONTEND_DIR", DEFAULT_FRONTEND))
    if os.environ.get("FIRECAL_FRONTEND_DIR") != "" and (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    return app


app = create_app()
