from dataclasses import dataclass

from yandex_ai_studio_sdk import AsyncAIStudio

from revu.application.entities.config import AIProfileConfig
from revu.application.entities.exceptions.ai_adapters_exceptions import NoAIResponse


@dataclass(frozen=True, slots=True)
class TextMessage:
    """One message of a YandexGPT request.

    The SDK accepts any object with ``role`` and ``text`` (its own
    ``TextMessageProtocol``), which is why this does not depend on the private
    message module it keeps its own types in.
    """

    role: str
    text: str


class YandexGPTAdapter:
    def __init__(self, profile: AIProfileConfig) -> None:
        self.profile = profile
        self._yandexgpt_client = AsyncAIStudio(
            folder_id=profile.folder_id,
            auth=profile.api_key,
        )

    async def get_chat_response(self, messages: list[TextMessage]) -> str:
        # Creating the model is synchronous in this SDK; only `run` is awaited.
        model = self._yandexgpt_client.models.completions(self.profile.model)

        response = await model.run(messages)

        text = response[0].text if response else None

        if not text:
            raise NoAIResponse("Yandex GPT returned no response")

        return text
