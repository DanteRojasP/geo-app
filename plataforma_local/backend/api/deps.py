"""Dependencias de FastAPI: Repository listo para usar."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from api.db import DataNotReady, Repository


def get_repo(request: Request) -> Repository:
    repo: Repository = request.app.state.repo
    try:
        repo.ensure_loaded()
    except DataNotReady as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return repo


RepoDep = Annotated[Repository, Depends(get_repo)]
