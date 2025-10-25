import json

from gigachat.models import Chat, Messages, MessagesRole

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import (
    GigaChatAdapter,
    get_gigachat_adapter,
)


class GigaChatPort(BaseAIPort):
    def __init__(self, adapter: GigaChatAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    @staticmethod
    def _get_chat(system_prompt: str, user_prompt: str) -> Chat:
        return Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(role=MessagesRole.USER, content=user_prompt),
            ]
        )

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        system_prompt = self.system_prompt or self._get_comment_prompt()
        chat = self._get_chat(
            system_prompt=system_prompt,
            user_prompt=self._get_diff_prompt(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        return await self.adapter.get_chat_response(payload=chat)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        system_prompt = self._get_prompt(git_provider)

        if self.system_prompt:
            system_prompt = self.system_prompt

        chat = self._get_chat(
            system_prompt=system_prompt,
            user_prompt=self._get_diff_prompt(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        output = await self.adapter.get_chat_response(payload=chat)

        try:
            serialized_output = json.loads(output)
        except json.decoder.JSONDecodeError:
            raise InvalidAIOutput("invalid JSON response from gigachat")

        return ReviewResponseDTO.from_request(
            general_comment=serialized_output["general_comment"],
            comments=serialized_output["comments"],
            git_provider=git_provider,
        )


def get_gigachat_port() -> GigaChatPort:
    return GigaChatPort(adapter=get_gigachat_adapter())
