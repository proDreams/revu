from openai import AsyncClient, Omit
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ParsedChatCompletion,
)
from pydantic import BaseModel

from revu.application.entities.config import AIProfileConfig
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class OpenAICompatibleAdapter:
    def __init__(self, http_client: HttpClientGateway, profile: AIProfileConfig):
        self._http_client = http_client
        self.profile = profile
        self._openai_client = AsyncClient(
            api_key=profile.api_key,
            http_client=self._http_client.get_client(),
            base_url=profile.base_url,
        )
        self.model = profile.model

    async def get_chat_response(
        self,
        messages: list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam],
        response_model: type[BaseModel] | Omit = None,  # type: ignore
    ) -> ParsedChatCompletion:
        if response_model is None:
            response_model = Omit()
        response: ParsedChatCompletion = await self._openai_client.chat.completions.parse(
            model=self.model,  # type: ignore
            messages=messages,
            response_format=response_model,
        )

        return response
