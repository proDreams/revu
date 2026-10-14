"""The webhook-facing use case: one event, one review.

The review itself belongs to :class:`ReviewRunner`. What is left here is what makes
it a *webhook* review: the per-connection concurrency budget, and turning a host
event into something the runner understands.
"""

from revu.application.entities.tenant import TenantContext
from revu.application.services.review_runner import (
    ReviewOutcome,
    ReviewRequest,
    ReviewRunner,
)
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO


class ReviewService:
    """Runs one review for one tenant.

    Stateless by design: the git port, the AI port, the review mode, the prompt and
    the concurrency budget all come from the :class:`TenantContext`, which is why a
    single instance can serve every configured connection. The runner is shared, and
    holds nothing but the context builder.
    """

    def __init__(self, runner: ReviewRunner) -> None:
        self._runner = runner

    async def process_webhook(self, tenant: TenantContext, webhook_data: PullRequestEventDTO) -> ReviewOutcome:
        """Run one review, waiting for a free slot of this connection.

        Reviews run in background tasks, so without a bound a burst of pushes
        would start an unlimited number of them, each holding a full diff in
        memory and calling the AI provider. The budget is per connection, so a
        noisy repository cannot starve the others.
        """
        async with tenant.review_slots:
            return await self._runner.run(
                reader=tenant.git_port,
                publisher=tenant.git_port,
                ai_port=tenant.ai_port,
                config=tenant.config,
                request=ReviewRequest(
                    repo=webhook_data.repo_full_name,
                    number=webhook_data.pr_number,
                    title=webhook_data.pr_title,
                    body=webhook_data.pr_body,
                    revision=webhook_data.commit_sha,
                ),
            )
