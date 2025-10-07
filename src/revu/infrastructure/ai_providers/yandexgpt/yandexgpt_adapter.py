from yandex_cloud_ml_sdk import YCloudML

from revu.application.config import get_settings
from revu.application.entities.exceptions.ai_adapters_exceptions import NoAIResponse


class YandexGPTAdapter:
    def __init__(self) -> None:
        self._ai_provider_config = get_settings().AI_PROVIDER_CONFIG
        self._yandexgpt_client = YCloudML(
            folder_id=self._ai_provider_config.AI_PROVIDER_FOLDER_ID, auth=self._ai_provider_config.AI_PROVIDER_API_KEY
        )

    async def get_chat_response(self, messages: list[dict[str, str]]) -> str:
        model = self._yandexgpt_client.models.completions(self._ai_provider_config.AI_PROVIDER_MODEL)

        response = model.run(messages)

        if response:
            return response[0].text
        else:
            raise NoAIResponse("Yandex GPT returned no response")


def get_yandexgpt_adapter() -> YandexGPTAdapter:
    return YandexGPTAdapter()
