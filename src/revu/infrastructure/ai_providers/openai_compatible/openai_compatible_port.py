from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from revu.application.config import get_settings
from revu.application.entities.default_prompts import (
    COMMENT_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
)
from revu.application.entities.enums.webhook_routes_enums import GitProviderEnum
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GiteaReviewResponse,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
    get_openai_compatible_adapter,
)


class OpenAICompatiblePort(AIProviderProtocol):
    def __init__(self, adapter: OpenAICompatibleAdapter) -> None:
        self.adapter = adapter
        self.system_prompt = get_settings().SYSTEM_PROMPT

    @staticmethod
    def _get_messages(
        prompt: str, diff: str
    ) -> list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam]:
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=prompt),
            ChatCompletionUserMessageParam(role="user", content=diff),
        ]

        return messages

    async def get_comment_response(self, diff: str) -> str:
        output = await self.adapter.get_chat_response(
            messages=self._get_messages(prompt=self.system_prompt or COMMENT_PROMPT, diff=diff)
        )

        return output.choices[0].message.content

    async def get_inline_response(self, diff: str, git_provider: str) -> ReviewResponseDTO:
        match git_provider:
            case GitProviderEnum.GITHUB:
                system_prompt = GITHUB_INLINE_PROMPT
                response_model = GithubReviewResponse
            case GitProviderEnum.GITEA:
                system_prompt = GITEA_INLINE_PROMPT
                response_model = GiteaReviewResponse
            case _:
                raise NotImplementedError()

        if self.system_prompt:
            system_prompt = self.system_prompt

        output = await self.adapter.get_chat_response(
            messages=self._get_messages(prompt=system_prompt, diff=diff), response_model=response_model
        )

        parsed_output = output.choices[0].message.parsed

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,
            comments=[comment.model_dump() for comment in parsed_output.comments],
            git_provider=git_provider,
        )


def get_openai_compatible_port() -> OpenAICompatiblePort:
    return OpenAICompatiblePort(adapter=get_openai_compatible_adapter())
