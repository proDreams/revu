import json
import re
from typing import Any

from pydantic import ValidationError

from revu.application.entities.default_prompts import (
    BITBUCKET_INLINE_PROMPT,
    BITBUCKET_RE_REVIEW_PROMPT,
    COMMENT_PROMPT,
    DIFF_PROMPT,
    GITEA_INLINE_PROMPT,
    GITEA_RE_REVIEW_PROMPT,
    GITHUB_INLINE_PROMPT,
    GITHUB_RE_REVIEW_PROMPT,
    GITLAB_INLINE_PROMPT,
    GITLAB_RE_REVIEW_PROMPT,
    RE_REVIEW_COMMENT_PROMPT,
)
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    BitbucketReviewResponse,
    GiteaReviewResponse,
    GithubReviewResponse,
    GitlabReviewResponse,
    InlineReviewResponse,
)
from revu.domain.entities.dto.review_context_dto import PreviousCommentDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol

# ```json\n{...}\n``` / ```\n{...}\n``` / ```{...}``` — the opening fence may
# carry a language hint, the closing one is optional.
_FENCED_JSON_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*(?P<body>.*?)(?:```)?\s*$", re.DOTALL)

# A pull request discussion can be long; the prompt only needs enough of it to
# recognise what was already raised, so both lists and each body are capped.
#: The surrounding code carries its own heading, because a model that comments on
#: code the pull request did not change turns a helpful review into noise.
CODE_CONTEXT_HEADER = """--- Surrounding code (not changed by this pull request) ---
Это тела изменённых функций, сигнатуры того, что они вызывают, и связанные тесты.
Комментировать можно только строки из диффа ниже: по этому коду инлайн-комментарии не оставляй.
Если проблема видна только здесь — скажи о ней в общем комментарии."""

CODE_CONTEXT_TRUNCATED = "Внимание: контекст приведён частично, лимит исчерпан."

MAX_CONTEXT_FINDINGS = 25
MAX_CONTEXT_DISCUSSION = 25
MAX_CONTEXT_BODY_CHARS = 600

RESOLVED_MARK = "помечено как исправленное"
OPEN_MARK = "не исправлено"


class BaseAIPort(AIProviderProtocol):
    """Prompt and output-schema selection shared by every AI vendor.

    Deliberately holds no configuration: a port instance is shared between git
    connections, so the prompt arrives with each :class:`ReviewTask`.
    """

    @staticmethod
    def _get_prompt(git_host: GitProviderEnum) -> str:
        match git_host:
            case GitProviderEnum.GITHUB:
                return GITHUB_INLINE_PROMPT
            case GitProviderEnum.GITEA:
                return GITEA_INLINE_PROMPT
            case GitProviderEnum.GITLAB:
                return GITLAB_INLINE_PROMPT
            case GitProviderEnum.BITBUCKET:
                return BITBUCKET_INLINE_PROMPT
            case _:
                raise UnknownGitProvider("unknown git provider")

    @staticmethod
    def _get_re_review_prompt(git_host: GitProviderEnum) -> str:
        """Instructions for a second look at a pull request ReVu already reviewed."""
        match git_host:
            case GitProviderEnum.GITHUB:
                return GITHUB_RE_REVIEW_PROMPT
            case GitProviderEnum.GITEA:
                return GITEA_RE_REVIEW_PROMPT
            case GitProviderEnum.GITLAB:
                return GITLAB_RE_REVIEW_PROMPT
            case GitProviderEnum.BITBUCKET:
                return BITBUCKET_RE_REVIEW_PROMPT
            case _:
                raise UnknownGitProvider("unknown git provider")

    @staticmethod
    def _get_comment_prompt() -> str:
        """Return the default comment prompt"""
        return COMMENT_PROMPT

    @staticmethod
    def _is_re_review(task: ReviewTask) -> bool:
        """A follow-up only when ReVu has findings of its own to verify.

        A pull request whose only comments are other people's is still a first
        review: there is nothing ReVu said that could have been addressed.
        """
        return task.previous_review is not None and task.previous_review.has_findings

    def _comment_instructions(self, task: ReviewTask) -> str:
        """Instructions for REVIEW_MODE=comment, extended by SYSTEM_PROMPT."""
        prompt = RE_REVIEW_COMMENT_PROMPT if self._is_re_review(task) else self._get_comment_prompt()

        return self._with_system_prompt(task.system_prompt, prompt)

    def _inline_instructions(self, task: ReviewTask) -> str:
        """Instructions for REVIEW_MODE=inline, extended by SYSTEM_PROMPT.

        ``SYSTEM_PROMPT`` is prepended rather than substituted: the inline
        prompt ends with the output schema, which providers such as GigaChat
        and YandexGPT rely on to emit parseable JSON.
        """
        prompt = (
            self._get_re_review_prompt(task.git_host) if self._is_re_review(task) else self._get_prompt(task.git_host)
        )

        return self._with_system_prompt(task.system_prompt, prompt)

    @staticmethod
    def _with_system_prompt(system_prompt: str | None, prompt: str) -> str:
        if not system_prompt:
            return prompt

        return f"{system_prompt}\n\n{prompt}"

    @classmethod
    def _get_diff_prompt(cls, task: ReviewTask) -> str:
        """Format the diff prompt with the task parameters.

        The earlier discussion travels in the same guarded block as the diff: a
        comment someone wrote is untrusted input like any other pull request text.
        """
        return DIFF_PROMPT.format(
            pr_title=task.pr_title,
            pr_body=task.pr_body or "(не указано)",
            previous_review=cls._render_previous_review(task),
            code_context=cls._render_code_context(task),
            diff=task.diff,
        )

    @classmethod
    def _render_code_context(cls, task: ReviewTask) -> str:
        """Describe the surrounding code, when the review was given any."""
        context = task.code_context

        if context is None or context.is_empty:
            return ""

        blocks = [CODE_CONTEXT_HEADER, ""]

        if context.stats.truncated:
            blocks.extend([CODE_CONTEXT_TRUNCATED, ""])

        for entry in context.entries:
            blocks.extend([f"[{entry.path}] {entry.title}", entry.text, ""])

        return "\n".join(blocks) + "\n"

    @classmethod
    def _render_previous_review(cls, task: ReviewTask) -> str:
        """Describe what the pull request already said, for a follow-up review."""
        context = task.previous_review

        if context is None or not cls._is_re_review(task):
            return ""

        # _is_re_review above guarantees at least one finding, so this list is never
        # empty; only the discussion is optional.
        findings = context.findings[-MAX_CONTEXT_FINDINGS:]
        sections = [
            "--- ReVu's earlier findings (check whether they were addressed) ---\n"
            + "\n".join(
                f"{position}. [{RESOLVED_MARK if comment.resolved else OPEN_MARK}] "
                f"{cls._describe_comment(comment, with_author=False)}"
                for position, comment in enumerate(findings, start=1)
            )
        ]

        discussion = context.discussion[-MAX_CONTEXT_DISCUSSION:]
        if discussion:
            sections.append(
                "--- Pull request discussion (context, not ReVu findings) ---\n"
                + "\n".join(f"- {cls._describe_comment(comment)}" for comment in discussion)
            )

        return "\n".join(sections) + "\n\n"

    @classmethod
    def _describe_comment(cls, comment: PreviousCommentDTO, with_author: bool = True) -> str:
        where = f"{comment.path}:{comment.line}" if comment.path else ""
        prefix = f"{where} — " if where else ""
        author = f"@{comment.author}: " if with_author and comment.author else ""

        return f"{author}{prefix}{cls._one_line(comment.body)}"

    @staticmethod
    def _one_line(text: str, limit: int = MAX_CONTEXT_BODY_CHARS) -> str:
        """Flatten a comment body and cap it, so one long comment cannot crowd out the diff."""
        flattened = " ".join(text.split())

        if len(flattened) <= limit:
            return flattened

        return flattened[: limit - 1].rstrip() + "…"

    @staticmethod
    def _get_response_model(git_host: GitProviderEnum) -> type[InlineReviewResponse]:
        match git_host:
            case GitProviderEnum.GITHUB:
                return GithubReviewResponse
            case GitProviderEnum.GITEA:
                return GiteaReviewResponse
            case GitProviderEnum.GITLAB:
                return GitlabReviewResponse
            case GitProviderEnum.BITBUCKET:
                return BitbucketReviewResponse
            case _:
                raise UnknownGitProvider("unknown git provider")

    @staticmethod
    def _parse_inline_payload(
        raw_output: str,
        provider: str,
        response_model: type[InlineReviewResponse],
    ) -> dict[str, Any]:
        """Decode the JSON review body of providers without schema enforcement.

        GigaChat and YandexGPT answer in free text, so the prompt is the only
        contract: an optional Markdown fence has to be stripped, the body has to
        be valid JSON, and it is then validated against the same pydantic model
        the structured-output providers use. Every failure surfaces as
        :class:`InvalidAIOutput` instead of a bare ``JSONDecodeError``,
        ``KeyError`` or ``ValidationError`` in a background task.
        """
        text = (raw_output or "").strip()

        if text.startswith("```"):
            match = _FENCED_JSON_RE.match(text)
            text = (match.group("body") if match else text).strip()

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            raise InvalidAIOutput(f"invalid JSON response from {provider}")

        if not isinstance(payload, dict):
            raise InvalidAIOutput(f"unexpected JSON response from {provider}: not an object")

        try:
            validated = response_model.model_validate(payload)
        except ValidationError as exc:
            raise InvalidAIOutput(f"JSON response from {provider} does not match the expected schema: {exc}")

        return {
            "general_comment": validated.general_comment,
            "comments": [comment.model_dump() for comment in validated.comments],
            "previous_findings": [finding.model_dump() for finding in validated.previous_findings],
        }
