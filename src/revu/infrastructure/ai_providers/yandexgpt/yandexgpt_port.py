import json

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.base import BaseAIPort
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
    YandexGPTAdapter,
    get_yandexgpt_adapter,
)


class YandexGPTPort(BaseAIPort):
    def __init__(self, adapter: YandexGPTAdapter) -> None:
        super().__init__()
        self.adapter = adapter

    @staticmethod
    def _get_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        return [{"role": "system", "text": system_prompt}, {"role": "user", "text": user_prompt}]

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        system_prompt = self.system_prompt or self._get_comment_prompt()

        messages = self._get_messages(
            system_prompt=system_prompt,
            user_prompt=self._get_diff_prompt(pr_title, pr_body, diff),
        )

        return await self.adapter.get_chat_response(messages=messages)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        system_prompt = self.system_prompt or self._get_prompt(git_provider)

        messages = self._get_messages(
            system_prompt=system_prompt,
            user_prompt=self._get_diff_prompt(pr_title, pr_body, diff),
        )

        output = await self.adapter.get_chat_response(messages=messages)

        # temporary solution
        if output.startswith("```") and output.endswith("```"):
            output = output[3:-3]

        try:
            serialized_output = json.loads(output)
        except json.decoder.JSONDecodeError:
            raise InvalidAIOutput("invalid JSON response from yandexgpt")

        return ReviewResponseDTO.from_request(
            general_comment=serialized_output["general_comment"],
            comments=serialized_output["comments"],
            git_provider=git_provider,
        )


def get_yandexgpt_port() -> YandexGPTPort:
    return YandexGPTPort(adapter=get_yandexgpt_adapter())
