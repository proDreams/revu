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
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    BitbucketReviewResponse,
    GiteaReviewResponse,
    GithubReviewResponse,
)
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol


class BaseAIPort(AIProviderProtocol):
    def __init__(self):
        self.system_prompt = str(get_settings().SYSTEM_PROMPT) if get_settings().SYSTEM_PROMPT else None

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

    @staticmethod
    def _get_diff_prompt(pr_title: str, pr_body: str | None, diff: str) -> str:
        """Format the diff prompt with provided parameters"""
        return DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff)

    @staticmethod
    def _get_response_model(git_provider: str):
        match git_provider:
            case GitProviderEnum.GITHUB:
                return GithubReviewResponse
            case GitProviderEnum.GITEA:
                return GiteaReviewResponse
            case GitProviderEnum.BITBUCKET:
                return BitbucketReviewResponse
            case _:
                raise UnknownGitProvider("unknown git provider")
