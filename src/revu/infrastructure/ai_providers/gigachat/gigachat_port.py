from gigachat.models import Chat, Messages, MessagesRole

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import GigaChatAdapter


class GigaChatPort(BaseAIPort):
    def __init__(self, adapter: GigaChatAdapter) -> None:
        self.adapter = adapter

    @staticmethod
    def _get_chat(system_prompt: str, user_prompt: str) -> Chat:
        return Chat(
            messages=[
                Messages(role=MessagesRole.SYSTEM, content=system_prompt),
                Messages(role=MessagesRole.USER, content=user_prompt),
            ]
        )

    async def get_comment_response(self, task: ReviewTask) -> str:
        chat = self._get_chat(
            system_prompt=self._comment_instructions(task),
            user_prompt=self._get_diff_prompt(task),
        )

        return await self.adapter.get_chat_response(payload=chat)

    async def get_inline_response(self, task: ReviewTask) -> ReviewResponseDTO:
        response_model = self._get_response_model(task.git_host)

        chat = self._get_chat(
            system_prompt=self._inline_instructions(task),
            user_prompt=self._get_diff_prompt(task),
        )

        output = await self.adapter.get_chat_response(payload=chat)

        payload = self._parse_inline_payload(output, provider="gigachat", response_model=response_model)

        return ReviewResponseDTO.from_request(
            general_comment=payload["general_comment"],
            comments=payload["comments"],
            git_host=task.git_host,
            previous_findings=payload["previous_findings"],
        )

    async def aclose(self) -> None:
        """This port owns its SDK transport, so the registry must close it."""
        await self.adapter.aclose()
