from typing import Annotated

from fastapi import APIRouter, BackgroundTasks
from fastapi.params import Depends
from starlette import status

from revu.application.services.webhook_service import WebhookService
from revu.presentation.webhooks.di import get_webhook_service
from revu.presentation.webhooks.mappers import gitea_to_domain, github_to_domain, bitbucket_to_domain
from revu.presentation.webhooks.schemas.github_schemas import (
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
    GitVersePullRequestWebhook,
    BitBucketRawPullRequestWebhook
)
from revu.presentation.webhooks.validators import (
    gitverse_validate_authorization,
    parse_gitea_webhook,
    parse_github_webhook,
)

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@webhooks_router.post(path="/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    webhook_data: Annotated[GithubPullRequestWebhook, Depends(parse_github_webhook)],
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    domain_event = github_to_domain(event=webhook_data)
    background_tasks.add_task(service.process_webhook, webhook_data=domain_event)


@webhooks_router.post(path="/gitea", status_code=status.HTTP_200_OK)
async def gitea_webhook(
    webhook_data: Annotated[GiteaPullRequestWebhook, Depends(parse_gitea_webhook)],
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    domain_event = gitea_to_domain(event=webhook_data)
    background_tasks.add_task(service.process_webhook, webhook_data=domain_event)
    
    
@webhooks_router.post(path='/bitbucket', status_code=status.HTTP_200_OK)
async def bitbucket_webhook(
    webhook_data: BitBucketRawPullRequestWebhook,
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    _webhook_data = webhook_data.to_bb()
    domain_event = bitbucket_to_domain(event=_webhook_data)
    background_tasks.add_task(service.process_webhook, webhook_data=domain_event)


@webhooks_router.post(path="/gitverse", status_code=status.HTTP_200_OK)
async def gitverse_webhook(
    webhook_data: GitVersePullRequestWebhook,
    _: Annotated[None, Depends(gitverse_validate_authorization)],
    background_tasks: BackgroundTasks,
    service: Annotated[WebhookService, Depends(get_webhook_service)],
) -> None:
    # domain_event = gitverse_to_domain(event=webhook_data)
    # background_tasks.add_task(service.process_webhook, webhook_data=domain_event)
    # Currently unavailable
    raise NotImplementedError()
