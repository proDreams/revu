import json

from gigachat.models import Chat, Messages, MessagesRole

from revu.application.config import get_settings
from revu.application.entities.default_prompts import (
    COMMENT_PROMPT,
    DIFF_PROMPT,
    GITEA_INLINE_PROMPT,
    GITHUB_INLINE_PROMPT,
)
from revu.application.entities.enums.webhook_routes_enums import GitProviderEnum
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.ai_provider_protocol import AIProviderProtocol
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import (
    GigaChatAdapter,
    get_gigachat_adapter,
)


class GigaChatPort(AIProviderProtocol):
    def __init__(self, adapter: GigaChatAdapter) -> None:
        self.adapter = adapter
        self.system_prompt = get_settings().SYSTEM_PROMPT

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
            system_prompt=self.system_prompt or COMMENT_PROMPT,
            user_prompt=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        return await self.adapter.get_chat_response(payload=chat)

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        match git_provider:
            case GitProviderEnum.GITHUB:
                system_prompt = GITHUB_INLINE_PROMPT
            case GitProviderEnum.GITEA:
                system_prompt = GITEA_INLINE_PROMPT
            case _:
                raise NotImplementedError()

        if self.system_prompt:
            system_prompt = self.system_prompt

        chat = self._get_chat(
            system_prompt=system_prompt,
            user_prompt=DIFF_PROMPT.format(pr_title=pr_title, pr_body=pr_body, diff=diff),
        )

        output = await self.adapter.get_chat_response(payload=chat)

        serialized_output = json.loads(output)

        return ReviewResponseDTO.from_request(
            general_comment=serialized_output["general_comment"],
            comments=serialized_output["comments"],
            git_provider=git_provider,
        )


def get_gigachat_port() -> GigaChatPort:
    return GigaChatPort(adapter=get_gigachat_adapter())
