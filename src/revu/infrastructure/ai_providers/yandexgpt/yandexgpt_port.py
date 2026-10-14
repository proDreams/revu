from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import YandexGPTAdapter


class YandexGPTPort(BaseAIPort):
    def __init__(self, adapter: YandexGPTAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    @staticmethod
    def _get_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        return [{"role": "system", "text": system_prompt}, {"role": "user", "text": user_prompt}]

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        messages = self._get_messages(
            system_prompt=self._comment_instructions(),
            user_prompt=self._get_diff_prompt(pr_title, pr_body, diff),
        )

        return await self.adapter.get_chat_response(messages=messages)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        response_model = self._get_response_model(git_provider)

        messages = self._get_messages(
            system_prompt=self._inline_instructions(git_provider),
            user_prompt=self._get_diff_prompt(pr_title, pr_body, diff),
        )

        output = await self.adapter.get_chat_response(messages=messages)

        payload = self._parse_inline_payload(output, provider="yandexgpt", response_model=response_model)

        return ReviewResponseDTO.from_request(
            general_comment=payload["general_comment"],
            comments=payload["comments"],
            git_provider=git_provider,
        )
