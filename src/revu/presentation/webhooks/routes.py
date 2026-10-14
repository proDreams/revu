from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, Request
from starlette import status

from revu.application.config import get_logger
from revu.application.entities.tenant import TenantContext
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.presentation.webhooks.validators import parse_webhook_event

logger = get_logger(name=__name__)

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"], route_class=DishkaRoute)


async def review_pull_request(
    service: WebhookService,
    tenant: TenantContext,
    event: PullRequestEventDTO,
) -> None:
    """Run a review in the background.

    Nothing consumes exceptions raised from a ``BackgroundTask``, so failures
    are caught here and logged instead of bubbling up into the worker.
    """
    try:
        await service.process_webhook(tenant=tenant, webhook_data=event)
    except Exception:
        logger.exception(
            "Review failed for connection %s, %s#%s",
            tenant.key,
            event.repo_full_name,
            event.pr_number,
        )


@webhooks_router.post(path="/{connection_key}", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    tenant: FromDishka[TenantContext],
    background_tasks: BackgroundTasks,
    service: FromDishka[WebhookService],
) -> None:
    """Accept a delivery for one configured connection.

    The connection is resolved from the URL (never from the body), its own secret
    verifies the signature, and its own AI profile runs the review.
    """
    webhook_data = await parse_webhook_event(request=request, tenant=tenant)
    background_tasks.add_task(review_pull_request, service, tenant, webhook_data)
