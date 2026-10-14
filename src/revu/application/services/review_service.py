from dataclasses import replace

from unidiff import PatchSet

from revu.application.config import get_logger
from revu.application.entities import review_marker
from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.application.entities.exceptions.review_service_exceptions import (
    ReviewModeException,
)
from revu.application.entities.tenant import TenantContext
from revu.application.services.diff_anchors import DiffAnchors, drop_unanchored_comments
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.dto.review_context_dto import ReviewContextDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask

logger = get_logger(name=__name__)


class ReviewService:
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

    async def _fetch_review_context(
        self,
        tenant: TenantContext,
        webhook_data: PullRequestEventDTO,
    ) -> ReviewContextDTO | None:
        """What the pull request already says, or ``None`` for a first review.

        Reading the history is how a second review avoids repeating itself, but it
        is not worth losing a review over: a host that refuses the call (an older
        token without the right scope, a blocked endpoint) costs only the context,
        and the review continues from the diff alone.
        """
        try:
            context = await tenant.git_port.fetch_review_context(
                repo=webhook_data.repo_full_name,
                index=webhook_data.pr_number,
            )
        except Exception:
            logger.warning(
                "could not read the earlier comments for connection %s, %s#%s; reviewing without them",
                tenant.key,
                webhook_data.repo_full_name,
                webhook_data.pr_number,
            )
            return None

        if context is None or tenant.config.include_pr_discussion:
            return context

        # ReVu's own findings are its own output; only other people's words are
        # held back when a connection asks for that.
        return ReviewContextDTO(comments=context.findings)

    @staticmethod
    def _progress_line(review: ReviewResponseDTO, context: ReviewContextDTO | None) -> str | None:
        """How many earlier findings were addressed, when that can be said.

        The total is ReVu's own count, so a model reporting fewer findings cannot
        shrink it; a model reporting none at all gets no line rather than a claim of
        zero fixes.
        """
        if context is None or not context.findings:
            return None

        total = len(context.findings)
        reported = review.previous_findings or []

        if not reported:
            logger.warning("no status reported for %d earlier findings; omitting the progress line", total)

            return None

        fixed = min(sum(1 for finding in reported if finding.is_fixed), total)
        line = f"📊 Из прошлых замечаний исправлено: {fixed} из {total}."

        return line + (" Все замечания закрыты." if fixed == total else f" Осталось: {total - fixed}.")

    @staticmethod
    def _is_re_review(context: ReviewContextDTO | None) -> bool:
        return context is not None and bool(context.findings)

    @classmethod
    def _sign_inline_review(
        cls,
        review: ReviewResponseDTO,
        context: ReviewContextDTO | None,
    ) -> ReviewResponseDTO:
        """Headline and sign the review, and sign every inline comment in it.

        The signature is what lets a later review tell ReVu's own words from the
        author's, which matters most when both use the same account.
        """
        progress = cls._progress_line(review, context)
        lines = [review_marker.header(re_review=cls._is_re_review(context))]
        lines.extend(line for line in (progress, review.general_comment) if line)
        comments = [replace(comment, body=review_marker.sign_inline(comment.body)) for comment in review.comments]

        return replace(review, general_comment=review_marker.mark("\n".join(lines)), comments=comments)

    @staticmethod
    def _sign_summary(text: str, context: ReviewContextDTO | None) -> str:
        """Comment mode publishes one comment; the model reports progress in its text."""
        header = review_marker.header(re_review=ReviewService._is_re_review(context))

        return review_marker.mark(f"{header}\n\n{text}")

    async def _run_review(self, tenant: TenantContext, webhook_data: PullRequestEventDTO) -> None:
        diff = await tenant.git_port.fetch_diff(
            repo=webhook_data.repo_full_name,
            index=webhook_data.pr_number,
        )

        context = await self._fetch_review_context(tenant, webhook_data)

        task = ReviewTask(
            diff=diff,
            git_host=tenant.config.host,
            pr_title=webhook_data.pr_title,
            pr_body=webhook_data.pr_body,
            system_prompt=tenant.config.system_prompt,
            previous_review=context,
        )

        match tenant.config.review_mode:
            case ReviewModeEnum.COMMENT:
                str_review = await tenant.ai_port.get_comment_response(task)

                await tenant.git_port.send_comment(
                    repo_owner=webhook_data.repo_full_name,
                    review=self._sign_summary(str_review, context),
                    index=webhook_data.pr_number,
                )
            case ReviewModeEnum.INLINE:
                annotated_diff = self.annotate_diff(diff_text=diff)

                dto_review = await tenant.ai_port.get_inline_response(replace(task, diff=annotated_diff))

                dto_review = self._sign_inline_review(dto_review, context)

                dto_review, dropped = drop_unanchored_comments(
                    dto_review,
                    DiffAnchors.from_diff(diff),
                    tenant.config.host,
                )

                if dropped:
                    logger.warning(
                        "dropped %d of %d inline comments for connection %s: their lines are not in the diff",
                        dropped,
                        dropped + len(dto_review.comments),
                        tenant.key,
                    )

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
