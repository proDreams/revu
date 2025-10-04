from openai import AsyncClient
from openai.types.responses import ParsedResponse
from pydantic import BaseModel

from revu.application.config import get_settings
from revu.infrastructure.http_client.http_client_gateway import (
    HttpClientGateway,
    get_http_gateway,
)


class OpenAIAdapter:
    def __init__(self, http_client: HttpClientGateway) -> None:
        self._http_client = http_client
        self._openai_client = AsyncClient(
            api_key=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_API_KEY,
            http_client=self._http_client.get_client(),
        )
        self.model = get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL

    async def get_chat_response(
        self,
        instructions: str,
        user_input: str,
        response_model: type[BaseModel] | None = None,
    ) -> ParsedResponse:
        response = await self._openai_client.responses.parse(
            model=self.model,
            instructions=instructions,
            input=user_input,
            text_format=response_model,
        )

        return response


def get_openai_adapter() -> OpenAIAdapter:
    return OpenAIAdapter(http_client=get_http_gateway())
