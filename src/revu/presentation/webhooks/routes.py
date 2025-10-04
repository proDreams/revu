from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from fastapi.params import Depends
from starlette import status

from revu.application.services.webhook_service import WebhookService
from revu.presentation.webhooks.di import get_webhook_service
from revu.presentation.webhooks.schemas import (
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from revu.presentation.webhooks.validators import verify_and_parse_github_webhook

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@webhooks_router.post(path="/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    webhook_data: Annotated[GithubPullRequestWebhook, Depends(verify_and_parse_github_webhook)],
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    background_tasks.add_task(service.process_webhook, webhook_data=webhook_data)


@webhooks_router.post(path="/gitea", status_code=status.HTTP_200_OK)
async def gitea_webhook(
    webhook_data: Annotated[GiteaPullRequestWebhook, Depends(verify_and_parse_github_webhook)],
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    background_tasks.add_task(service.process_webhook, webhook_data=webhook_data)
