from gigachat.client import GigaChatAsyncClient as GigaChat
from gigachat.models import Chat

from revu.application.entities.config import AIProfileConfig


class GigaChatAdapter:
    def __init__(self, profile: AIProfileConfig) -> None:
        self.profile = profile
        self._gigachat_client = GigaChat(
            credentials=profile.api_key,
            scope=profile.scope,
            model=profile.model,
        )

    async def get_chat_response(self, payload: Chat) -> str:
        response = await self._gigachat_client.achat(payload=payload)

        return response.choices[0].message.content

    async def aclose(self) -> None:
        """Release the SDK's HTTP client when the container shuts down."""
        await self._gigachat_client.aclose()
