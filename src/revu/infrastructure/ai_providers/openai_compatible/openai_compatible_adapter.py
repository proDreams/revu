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
            # The SDK is typed against its own httpx build, which is not the
            # one we depend on; the boundary tests drive the real client through
            # our transport, so the mismatch is in the stubs, not at runtime.
            http_client=self._http_client.get_client(),  # type: ignore[arg-type]
            base_url=profile.base_url,
            # Our HTTP client is built for the Git hosts and its timeout is far too
            # short for a model reading a whole diff; the SDK takes its own here.
            timeout=profile.timeout,
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
