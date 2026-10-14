from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
    TextMessage,
    YandexGPTAdapter,
)


class YandexGPTPort(BaseAIPort):
    def __init__(self, adapter: YandexGPTAdapter) -> None:
        self.adapter = adapter

    @staticmethod
    def _get_messages(system_prompt: str, user_prompt: str) -> list[TextMessage]:
        return [
            TextMessage(role="system", text=system_prompt),
            TextMessage(role="user", text=user_prompt),
        ]

    async def get_comment_response(self, task: ReviewTask) -> str:
        messages = self._get_messages(
            system_prompt=self._comment_instructions(task),
            user_prompt=self._get_diff_prompt(task),
        )

        return await self.adapter.get_chat_response(messages=messages)

    async def get_inline_response(self, task: ReviewTask) -> ReviewResponseDTO:
        response_model = self._get_response_model(task.git_host)

        messages = self._get_messages(
            system_prompt=self._inline_instructions(task),
            user_prompt=self._get_diff_prompt(task),
        )

        output = await self.adapter.get_chat_response(messages=messages)

        payload = self._parse_inline_payload(output, provider="yandexgpt", response_model=response_model)

        return ReviewResponseDTO.from_request(
            general_comment=payload["general_comment"],
            comments=payload["comments"],
            git_host=task.git_host,
            previous_findings=payload["previous_findings"],
        )
