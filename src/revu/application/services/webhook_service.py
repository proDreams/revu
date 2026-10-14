from dataclasses import replace

from unidiff import PatchSet

from revu.application.entities.enums.webhook_service_enums import ReviewModeEnum
from revu.application.entities.exceptions.webhook_service_exceptions import (
    ReviewModeException,
)
from revu.application.entities.tenant import TenantContext
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask


class WebhookService:
    """Runs one review for one tenant.

    Stateless by design: the git port, the AI port, the review mode, the prompt
    and the concurrency budget all come from the :class:`TenantContext`, which is
    why a single instance can serve every configured connection.
    """

    async def process_webhook(self, tenant: TenantContext, webhook_data: PullRequestEventDTO) -> None:
        """Run one review, waiting for a free slot of this connection.

        Reviews run in background tasks, so without a bound a burst of pushes
        would start an unlimited number of them, each holding a full diff in
        memory and calling the AI provider. The budget is per connection, so a
        noisy repository cannot starve the others.
        """
        async with tenant.review_slots:
            await self._run_review(tenant=tenant, webhook_data=webhook_data)

    async def _run_review(self, tenant: TenantContext, webhook_data: PullRequestEventDTO) -> None:
        diff = await tenant.git_port.fetch_diff(
            repo=webhook_data.repo_full_name,
            index=webhook_data.pr_number,
        )

        task = ReviewTask(
            diff=diff,
            git_host=tenant.config.host,
            pr_title=webhook_data.pr_title,
            pr_body=webhook_data.pr_body,
            system_prompt=tenant.config.system_prompt,
        )

        match tenant.config.review_mode:
            case ReviewModeEnum.COMMENT:
                str_review = await tenant.ai_port.get_comment_response(task)

                await tenant.git_port.send_comment(
                    repo_owner=webhook_data.repo_full_name,
                    review=str_review,
                    index=webhook_data.pr_number,
                )
            case ReviewModeEnum.INLINE:
                annotated_diff = self.annotate_diff(diff_text=diff)

                dto_review = await tenant.ai_port.get_inline_response(replace(task, diff=annotated_diff))

                await tenant.git_port.send_inline(
                    sha=webhook_data.commit_sha,
                    repo_owner=webhook_data.repo_full_name,
                    review=dto_review,
                    index=webhook_data.pr_number,
                )
            case _:
                raise ReviewModeException("Unknown review mode")

    @staticmethod
    def annotate_diff(diff_text: str) -> str:
        patch = PatchSet(diff_text)
        out: list[str] = []

        for f in patch:
            src = f.source_file
            dst = f.target_file

            out.append(f"diff --git {src} {dst}")

            if getattr(f, "is_added_file", False) or getattr(f, "is_new_file", False):
                out.append("new file mode 100644")
            if getattr(f, "is_removed_file", False):
                out.append("deleted file mode 100644")

            out.append(f"--- {src}")
            out.append(f"+++ {dst}")

            for h in f:
                src_len = h.source_length or 0
                dst_len = h.target_length or 0
                out.append(f"@@ -{h.source_start},{src_len} +{h.target_start},{dst_len} @@")

                old_ln = h.source_start
                new_ln = h.target_start

                for ln in h:
                    text = ln.value.rstrip("\n")

                    if ln.is_context:
                        out.append(f"  [{old_ln}->{new_ln}] {text}")
                        old_ln += 1
                        new_ln += 1
                    elif ln.is_removed:
                        out.append(f"- [{old_ln}] {text}")
                        old_ln += 1
                    elif ln.is_added:
                        out.append(f"+ [{new_ln}] {text}")
                        new_ln += 1

        return "\n".join(out)
