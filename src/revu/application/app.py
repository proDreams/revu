from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from revu.application.config import get_logger
from revu.application.di import create_container
from revu.application.services.webhook_service import WebhookService
from revu.presentation.webhooks.routes import webhooks_router

logger = get_logger(name=__name__)


async def _validation_error_handler(_: Request, exc: ValidationError) -> JSONResponse:
    """A payload rejected by pydantic is a client error, not a server error."""
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    container = app.state.dishka_container
    # Resolve the whole graph once, so a misconfigured provider fails at
    # startup rather than on the first webhook.
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
    app.add_exception_handler(ValidationError, _validation_error_handler)
    setup_dishka(container=create_container(), app=app)

    return app


def run_app():
    uvicorn.run(create_app(), host="0.0.0.0", port=8000, loop="asyncio", log_config=None)
