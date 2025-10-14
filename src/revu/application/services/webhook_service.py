from unidiff import PatchSet

from revu.application.config import get_settings
from revu.application.entities.enums.webhook_service_enums import ReviewModeEnum
from revu.application.entities.exceptions.webhook_service_exceptions import (
    ReviewModeException,
)
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.application.services.statistics import StatisticsService


class WebhookService:
    def __init__(self, ai_port: AIProviderProtocol, git_port: GitProviderProtocol) -> None:
        self.ai_port = ai_port
        self.git_port = git_port
        self.stats = StatisticsService()

    async def process_webhook(self, webhook_data: PullRequestEventDTO) -> None:
        await self.stats.add_review(repo_name=webhook_data.repo_full_name)
        requested_diff = await self.git_port.fetch_diff(
            repo=webhook_data.repo_full_name,
            index=webhook_data.pr_number,
        )

        diff = requested_diff.decode() if isinstance(requested_diff, bytes) else requested_diff

        match get_settings().REVIEW_MODE:
            case ReviewModeEnum.COMMENT:
                str_review = await self.ai_port.get_comment_response(
                    diff=diff, pr_title=webhook_data.pr_title, pr_body=webhook_data.pr_body
                )

                await self.git_port.send_comment(
                    repo_owner=webhook_data.repo_full_name,
                    review=str_review,
                    index=webhook_data.pr_number,
                )
            case ReviewModeEnum.INLINE:
                annotated_diff = self.annotate_diff(diff_text=diff)

                dto_review = await self.ai_port.get_inline_response(
                    diff=annotated_diff,
                    git_provider=get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER,
                    pr_title=webhook_data.pr_title,
                    pr_body=webhook_data.pr_body,
                )

                await self.git_port.send_inline(
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

                    if text.startswith("\\ No newline at end of file"):
                        out.append(text)
                        continue

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
