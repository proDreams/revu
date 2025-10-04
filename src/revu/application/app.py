import uvicorn
from fastapi import FastAPI

from revu.application.config import get_logger
from revu.presentation.webhooks.routes import webhooks_router

logger = get_logger(name=__name__)


def run_app():
    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    app.include_router(webhooks_router)

    uvicorn.run(app, host="0.0.0.0", port=8000, loop="asyncio", log_config=None)
