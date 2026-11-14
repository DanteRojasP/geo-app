"""Fixtures comunes: configuración aislada en modo sintético, sin depender de un .env local."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from firecal.settings import EnvSettings, Settings, build_settings, get_settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Fuerza modo sintético y quita la MAP_KEY para que los tests no dependan del entorno."""
    monkeypatch.setenv("FIRECAL_DATA_MODE", "synthetic")
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return build_settings(EnvSettings(_env_file=None))


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))


@pytest.fixture(scope="session")
def pipeline_home(tmp_path_factory):
    """Pipeline sintético completo (synth -> ... -> validate) en una carpeta aislada.

    Se construye una sola vez por sesión y lo comparten los tests de armonización y de la API.
    """
    import shutil
    from datetime import date
    from types import SimpleNamespace

    from firecal.pipeline import (
        run_aggregate,
        run_clean,
        run_harmonize,
        run_ingest,
        run_validate,
    )
    from firecal.settings import PROJECT_ROOT, Paths, ScientificParams, load_params
    from firecal.synth.generator import generate

    home = tmp_path_factory.mktemp("pipeline_home")
    shutil.copytree(PROJECT_ROOT / "config", home / "config")
    raw = load_params(home / "config" / "settings.yaml").model_dump()
    raw["harmonization"]["bootstrap_reps"] = 200  # suficiente para probar la lógica
    raw["api"]["rate_limit"]["enabled"] = False  # se prueba aparte en test_limits.py
    env = EnvSettings(_env_file=None, FIRECAL_DATA_MODE="synthetic")
    settings = Settings(env=env, params=ScientificParams.model_validate(raw),
                        paths=Paths(home=home))
    generate(settings, scale=0.25, start=date(2000, 11, 1), end=date(2026, 11, 12))
    run_ingest(settings)
    run_clean(settings)
    run_aggregate(settings)
    summary = run_harmonize(settings)
    metrics = run_validate(settings)
    from firecal.plan.events import build_events

    plan_meta = build_events(settings)
    return SimpleNamespace(settings=settings, summary=summary, metrics=metrics,
                           plan_meta=plan_meta)
