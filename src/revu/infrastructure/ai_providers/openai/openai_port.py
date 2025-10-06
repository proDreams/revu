from revu.application.config import get_settings
from revu.application.entities.default_prompts import (
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
    GiteaReviewResponse,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.infrastructure.ai_providers.openai.openai_adapter import (
    OpenAIAdapter,
    get_openai_adapter,
)


class OpenAIPort(AIProviderProtocol):
    def __init__(self, adapter: OpenAIAdapter) -> None:
        self.adapter = adapter
        self.system_prompt = get_settings().SYSTEM_PROMPT

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        output = await self.adapter.get_chat_response(
            user_input=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
            instructions=self.system_prompt or COMMENT_PROMPT,
        )

        return output.output_parsed

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        match git_provider:
            case GitProviderEnum.GITHUB:
                system_prompt = GITHUB_INLINE_PROMPT
                response_model = GithubReviewResponse
            case GitProviderEnum.GITEA:
                system_prompt = GITEA_INLINE_PROMPT
                response_model = GiteaReviewResponse
            case _:
                raise UnknownGitProvider("unknown git provider")

        if self.system_prompt:
            system_prompt = self.system_prompt

        output = await self.adapter.get_chat_response(
            user_input=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
            instructions=system_prompt,
            response_model=response_model,
        )

        parsed_output = output.output_parsed

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,
            comments=[comment.model_dump() for comment in parsed_output.comments],
            git_provider=git_provider,
        )


def get_openai_port() -> OpenAIPort:
    return OpenAIPort(adapter=get_openai_adapter())
