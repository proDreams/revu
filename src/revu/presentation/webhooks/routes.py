from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, BackgroundTasks, Request
from starlette import status

from revu.application.config import get_logger
from revu.application.entities.tenant import TenantContext
from revu.application.services.failure_notice import failure_notice
from revu.application.services.review_service import ReviewService
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.infrastructure.logger.connection_context import (
    reset_connection_key,
    set_connection_key,
)
from revu.presentation.webhooks.validators import parse_webhook_event

logger = get_logger(name=__name__)

webhooks_router = APIRouter(prefix="/webhooks", tags=["Webhooks"], route_class=DishkaRoute)


async def review_pull_request(
    service: ReviewService,
    tenant: TenantContext,
    event: PullRequestEventDTO,
) -> None:
    """Run a review in the background.

    Nothing consumes exceptions raised from a ``BackgroundTask``, so failures are
    caught here, logged, and — unless the connection turns it off — reported on
    the pull request itself. A bot that only logs into the void looks like it
    worked.
    """
    logger.info(
        "Reviewing %s#%s (%s, action %s) on connection %s",
        event.repo_full_name,
        event.pr_number,
        tenant.config.host.value,
        event.action,
        tenant.key,
    )

    # Every record emitted while this task runs carries the connection key,
    # including the ones from httpx and the provider SDKs.
    token = set_connection_key(tenant.key)

    try:
        await service.process_webhook(tenant=tenant, webhook_data=event)
    except Exception as exc:
        logger.exception(
            "Review failed for connection %s, %s#%s",
            tenant.key,
            event.repo_full_name,
            event.pr_number,
        )

        if tenant.config.notify_on_failure:
            await publish_failure_notice(tenant, event, exc)
    finally:
        reset_connection_key(token)


async def publish_failure_notice(
    tenant: TenantContext,
    event: PullRequestEventDTO,
    exc: BaseException,
) -> None:
    """Tell the pull request that the review failed.

    Best effort by design: a failing notice is logged, never raised, so it can
    neither mask the original error nor start a loop.
    """
    try:
        await tenant.git_port.send_comment(
            repo_owner=event.repo_full_name,
            review=failure_notice(exc),
            index=event.pr_number,
        )
    except Exception:
        logger.exception(
            "Could not publish the failure notice for connection %s, %s#%s",
            tenant.key,
            event.repo_full_name,
            event.pr_number,
        )


@webhooks_router.post(path="/{connection_key}", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    tenant: FromDishka[TenantContext],
    background_tasks: BackgroundTasks,
    service: FromDishka[ReviewService],
) -> None:
    """Accept a delivery for one configured connection.

    The connection is resolved from the URL (never from the body), its own secret
    verifies the signature, and its own AI profile runs the review.
    """
    webhook_data = await parse_webhook_event(request=request, tenant=tenant)
    background_tasks.add_task(review_pull_request, service, tenant, webhook_data)
