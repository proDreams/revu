from typing import Annotated

from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.params import Depends
from starlette import status

from revu.application.config import get_logger
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.presentation.webhooks.mappers import (
    bitbucket_to_domain,
    gitea_to_domain,
    github_to_domain,
)
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
    GitVersePullRequestWebhook,
)
from revu.presentation.webhooks.validators import (
    gitverse_validate_authorization,
    parse_bitbucket_webhook,
    parse_gitea_webhook,
    parse_github_webhook,
)

logger = get_logger(name=__name__)

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"], route_class=DishkaRoute)


async def review_pull_request(service: WebhookService, event: PullRequestEventDTO) -> None:
    """Run a review in the background.

    Nothing consumes exceptions raised from a ``BackgroundTask``, so failures
    are caught here and logged instead of bubbling up into the worker.
    """
    try:
        await service.process_webhook(webhook_data=event)
    except Exception:
        logger.exception("Review failed for %s#%s", event.repo_full_name, event.pr_number)


@webhooks_router.post(path="/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    webhook_data: Annotated[GithubPullRequestWebhook, Depends(parse_github_webhook)],
    background_tasks: BackgroundTasks,
    service: FromDishka[WebhookService],
) -> None:
    domain_event = github_to_domain(event=webhook_data)
    background_tasks.add_task(review_pull_request, service, domain_event)


@webhooks_router.post(path="/gitea", status_code=status.HTTP_200_OK)
async def gitea_webhook(
    webhook_data: Annotated[GiteaPullRequestWebhook, Depends(parse_gitea_webhook)],
    background_tasks: BackgroundTasks,
    service: FromDishka[WebhookService],
) -> None:
    domain_event = gitea_to_domain(event=webhook_data)
    background_tasks.add_task(review_pull_request, service, domain_event)


@webhooks_router.post(path="/bitbucket", status_code=status.HTTP_200_OK)
async def bitbucket_webhook(
    webhook_data: Annotated[BitBucketRawPullRequestWebhook, Depends(parse_bitbucket_webhook)],
    background_tasks: BackgroundTasks,
    service: FromDishka[WebhookService],
) -> None:
    domain_event = bitbucket_to_domain(event=webhook_data.to_bb())
    background_tasks.add_task(review_pull_request, service, domain_event)


@webhooks_router.post(path="/gitverse", status_code=status.HTTP_200_OK)
async def gitverse_webhook(
    webhook_data: GitVersePullRequestWebhook,
    _: Annotated[None, Depends(gitverse_validate_authorization)],
) -> None:
    # Payload shape and auth are validated above, but the integration itself
    # was never finished. 501 states that explicitly instead of crashing the
    # worker with NotImplementedError.
    logger.warning(
        "GitVerse webhook received for %s, integration is not implemented", webhook_data.repository.full_name
    )
    raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="GitVerse integration is not implemented")
