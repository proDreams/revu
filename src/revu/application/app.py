from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from revu.application.config import get_logger, get_settings, validate_settings
from revu.application.di import create_container
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.exceptions.base import CoreException
from revu.presentation.health import health_router
from revu.presentation.webhooks.routes import webhooks_router
from revu.presentation.webhooks.validators import ReviewNotNeededError

logger = get_logger(name=__name__)


async def _validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
    """A payload rejected by pydantic is a client error, not a server error."""
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


async def _review_not_needed_handler(_: Request, exc: ReviewNotNeededError) -> JSONResponse:
    """Acknowledge a delivery ReVu has nothing to do for, so hosts do not retry."""
    return JSONResponse(status_code=200, content={"detail": exc.reason})


async def _core_exception_handler(_: Request, exc: CoreException) -> JSONResponse:
    """Turn an expected domain failure into a 500 without leaking internals."""
    logger.exception("Unhandled application error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal application error"})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Validate the configuration, then resolve the whole graph once, so a
    # misconfigured provider fails at startup rather than on the first webhook.
    validate_settings()
    container = app.state.dishka_container
    await container.get(WebhookService)

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
    app.add_exception_handler(CoreException, _core_exception_handler)
    setup_dishka(container=create_container(), app=app)

    return app


def run_app():
    settings = get_settings()

    uvicorn.run(
        create_app(),
        host=settings.get("APP_HOST", "0.0.0.0"),
        port=settings.get("APP_PORT", 8000),
        loop="asyncio",
        log_config=None,
    )
