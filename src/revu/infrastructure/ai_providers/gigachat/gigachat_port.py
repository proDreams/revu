from gigachat.models import Chat, Messages, MessagesRole

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import GigaChatAdapter


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
        chat = self._get_chat(
            system_prompt=self._comment_instructions(),
            user_prompt=self._get_diff_prompt(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        return await self.adapter.get_chat_response(payload=chat)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        response_model = self._get_response_model(git_provider)

        chat = self._get_chat(
            system_prompt=self._inline_instructions(git_provider),
            user_prompt=self._get_diff_prompt(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        output = await self.adapter.get_chat_response(payload=chat)

        payload = self._parse_inline_payload(output, provider="gigachat", response_model=response_model)

        return ReviewResponseDTO.from_request(
            general_comment=payload["general_comment"],
            comments=payload["comments"],
            git_provider=git_provider,
        )
