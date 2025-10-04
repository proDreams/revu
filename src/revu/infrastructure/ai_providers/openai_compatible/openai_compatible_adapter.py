from openai import AsyncClient, Omit
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ParsedChatCompletion,
)
from pydantic import BaseModel

from revu.application.config import get_settings
from revu.infrastructure.http_client.http_client_gateway import (
    HttpClientGateway,
    get_http_gateway,
)


class OpenAICompatibleAdapter:
    def __init__(self, http_client: HttpClientGateway):
        self._http_client = http_client
        self._openai_client = AsyncClient(
            api_key=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_API_KEY,
            http_client=self._http_client.get_client(),
            base_url=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_BASE_URL,
        )
        self.model = get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL

    async def get_chat_response(
        self,
        messages: list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam],
        response_model: type[BaseModel] | Omit = None,
    ) -> ParsedChatCompletion:
        if response_model is None:
            response_model = Omit()
        response: ParsedChatCompletion = await self._openai_client.chat.completions.parse(
            model=self.model,
            messages=messages,
            response_format=response_model,
        )

        return response


def get_openai_compatible_adapter() -> OpenAICompatibleAdapter:
    return OpenAICompatibleAdapter(http_client=get_http_gateway())
