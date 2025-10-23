from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
    get_openai_compatible_adapter,
)
from revu.infrastructure.ai_providers.base import BaseAIPort


class OpenAICompatiblePort(BaseAIPort):
    def __init__(self, adapter: OpenAICompatibleAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    @staticmethod
    def _get_messages(
        system_prompt: str, user_prompt: str
    ) -> list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam]:
        messages = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
            ChatCompletionUserMessageParam(role="user", content=user_prompt),
        ]

        return messages

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        system_prompt = self.system_prompt or self._get_comment_prompt()
        user_prompt = self._get_diff_prompt(pr_title, pr_body, diff)
        output = await self.adapter.get_chat_response(
            messages=self._get_messages(system_prompt=system_prompt, user_prompt=user_prompt)
        )

        return output.choices[0].message.content  # type: ignore

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        system_prompt = self._get_prompt(git_provider)
        
        if self.system_prompt:
            system_prompt = self.system_prompt

        response_model = self._get_response_model(git_provider)

        user_prompt = self._get_diff_prompt(pr_title, pr_body, diff)

        output = await self.adapter.get_chat_response(
            messages=self._get_messages(system_prompt=system_prompt, user_prompt=user_prompt),
            response_model=response_model,
        )

        parsed_output = output.choices[0].message.parsed

        return ReviewResponseDTO.from_request(
            general_comment=parsed_output.general_comment,  # type: ignore
            comments=[comment.model_dump() for comment in parsed_output.comments],  # type: ignore
            git_provider=git_provider,
        )
    


def get_openai_compatible_port() -> OpenAICompatiblePort:
    return OpenAICompatiblePort(adapter=get_openai_compatible_adapter())
