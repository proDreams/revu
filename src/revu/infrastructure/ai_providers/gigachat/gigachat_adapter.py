from gigachat.client import GigaChatAsyncClient as GigaChat
from gigachat.models import Chat

from revu.application.config import get_settings


class GigaChatAdapter:
    def __init__(self) -> None:
        self._gigachat_client = GigaChat(
            credentials=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_API_KEY,  # type: ignore
            scope=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_SCOPE,  # type: ignore
            model=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL,  # type: ignore
        )

    async def get_chat_response(self, payload: Chat) -> str:
        response = await self._gigachat_client.achat(payload=payload)

        return response.choices[0].message.content


def get_gigachat_adapter() -> GigaChatAdapter:
    return GigaChatAdapter()
