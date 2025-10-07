import json

from revu.application.config import get_settings
from revu.application.entities.default_prompts import (
    COMMENT_PROMPT,
    DIFF_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
)
from revu.application.entities.enums.webhook_routes_enums import GitProviderEnum
from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
    YandexGPTAdapter,
    get_yandexgpt_adapter,
)


class YandexGPTPort(AIProviderProtocol):
    def __init__(self, adapter: YandexGPTAdapter) -> None:
        self.adapter = adapter
        self.system_prompt = get_settings().SYSTEM_PROMPT

    @staticmethod
    def _get_messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
        return [{"role": "system", "text": system_prompt}, {"role": "user", "text": user_prompt}]

    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        messages = self._get_messages(
            system_prompt=self.system_prompt or COMMENT_PROMPT,
            user_prompt=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        return await self.adapter.get_chat_response(messages=messages)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        match git_provider:
            case GitProviderEnum.GITHUB:
                system_prompt = GITHUB_INLINE_PROMPT
            case GitProviderEnum.GITEA:
                system_prompt = GITEA_INLINE_PROMPT
            case _:
                raise UnknownGitProvider("unknown git provider")

        if self.system_prompt:
            system_prompt = self.system_prompt

        messages = self._get_messages(
            system_prompt=system_prompt,
            user_prompt=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
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
