from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

import uvicorn
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from revu.application.config import get_logger, load_settings
from revu.application.di import create_container
from revu.application.entities.config import Settings, UnknownConnectionError
from revu.application.registry.git_connections import GitConnectionRegistry
from revu.application.services.review_service import ReviewService
from revu.domain.entities.exceptions.base import CoreException
from revu.presentation.health import health_router
from revu.presentation.webhooks.routes import webhooks_router
from revu.presentation.webhooks.validators import ReviewNotNeededError

logger = get_logger(name=__name__)


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """A payload rejected by pydantic is a client error, not a server error."""
    errors = cast(ValidationError, exc).errors()

    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


async def _review_not_needed_handler(_: Request, exc: Exception) -> JSONResponse:
    """Acknowledge a delivery ReVu has nothing to do for, so hosts do not retry."""
    return JSONResponse(status_code=200, content={"detail": cast(ReviewNotNeededError, exc).reason})


async def _unknown_connection_handler(_: Request, exc: Exception) -> JSONResponse:
    """A webhook for a connection that is not configured is a plain 404."""
    logger.warning("webhook for unknown connection: %s", exc)
    return JSONResponse(status_code=404, content={"detail": "Unknown webhook connection"})


async def _core_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Turn an expected domain failure into a 500 without leaking internals."""
    logger.exception("Unhandled application error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal application error"})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Resolving Settings parses and validates the configuration; resolving the
    # service afterwards builds the rest of the graph. A misconfigured
    # connection therefore fails at startup, not on the first webhook.
    container = app.state.dishka_container
    settings = await container.get(Settings)
    await container.get(ReviewService)

    connections = await container.get(GitConnectionRegistry)
    logger.info(
        "configured git connections: %s; default AI profile: %s",
        ", ".join(f"{key} ({host})" for key, host in connections.hosts().items()),
        settings.default_ai_provider,
    )

    try:
        yield
    finally:
        await container.close()


def create_app() -> FastAPI:
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )

    app.include_router(webhooks_router)
    app.include_router(health_router)
    app.add_exception_handler(ValidationError, _validation_error_handler)
    app.add_exception_handler(ReviewNotNeededError, _review_not_needed_handler)
    app.add_exception_handler(UnknownConnectionError, _unknown_connection_handler)
    app.add_exception_handler(CoreException, _core_exception_handler)
    setup_dishka(container=create_container(), app=app)

    return app


def run_app():
    settings = load_settings()

    uvicorn.run(
        create_app(),
        host=settings.app.host,
        port=settings.app.port,
        loop="asyncio",
        log_config=None,
    )
