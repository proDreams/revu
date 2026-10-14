import json
import re
from typing import Any

from pydantic import ValidationError

from revu.application.config import get_settings
from revu.application.entities.default_prompts import (
    BITBUCKET_INLINE_PROMPT,
    COMMENT_PROMPT,
    DIFF_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
)
from revu.application.entities.enums.webhook_routes_enums import GitProviderEnum
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    BitbucketReviewResponse,
    GiteaReviewResponse,
    GithubReviewResponse,
    ReviewResponse,
)
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol

# ```json\n{...}\n``` / ```\n{...}\n``` / ```{...}``` — the opening fence may
# carry a language hint, the closing one is optional.
_FENCED_JSON_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*(?P<body>.*?)(?:```)?\s*$", re.DOTALL)


class BaseAIPort(AIProviderProtocol):
    def __init__(self):
        system_prompt = get_settings().SYSTEM_PROMPT
        self.system_prompt = str(system_prompt).strip() if system_prompt else None

    @staticmethod
    def _get_prompt(git_provider: str) -> str:
        match git_provider:
            case GitProviderEnum.GITHUB:
                return GITHUB_INLINE_PROMPT
            case GitProviderEnum.GITEA:
                return GITEA_INLINE_PROMPT
            case GitProviderEnum.BITBUCKET:
                return BITBUCKET_INLINE_PROMPT
            case _:
                raise UnknownGitProvider("unknown git provider")

    @staticmethod
    def _get_comment_prompt() -> str:
        """Return the default comment prompt"""
        return COMMENT_PROMPT

    def _comment_instructions(self) -> str:
        """Instructions for REVIEW_MODE=comment, extended by SYSTEM_PROMPT."""
        return self._with_system_prompt(self._get_comment_prompt())

    def _inline_instructions(self, git_provider: str) -> str:
        """Instructions for REVIEW_MODE=inline, extended by SYSTEM_PROMPT.

        ``SYSTEM_PROMPT`` is prepended rather than substituted: the inline
        prompt ends with the output schema, which providers such as GigaChat
        and YandexGPT rely on to emit parseable JSON.
        """
        return self._with_system_prompt(self._get_prompt(git_provider))

    def _with_system_prompt(self, prompt: str) -> str:
        if not self.system_prompt:
            return prompt

        return f"{self.system_prompt}\n\n{prompt}"

    @staticmethod
    def _get_diff_prompt(pr_title: str, pr_body: str | None, diff: str) -> str:
        """Format the diff prompt with provided parameters"""
        return DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff)

    @staticmethod
    def _get_response_model(git_provider: str) -> type[ReviewResponse]:
        match git_provider:
            case GitProviderEnum.GITHUB:
                return GithubReviewResponse
            case GitProviderEnum.GITEA:
                return GiteaReviewResponse
            case GitProviderEnum.BITBUCKET:
                return BitbucketReviewResponse
            case _:
                raise UnknownGitProvider("unknown git provider")

    @staticmethod
    def _parse_inline_payload(
        raw_output: str,
        provider: str,
        response_model: type[ReviewResponse],
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
        }
