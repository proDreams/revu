from typing import Any

from openai import AsyncClient
from openai.types.responses import ParsedResponse
from pydantic import BaseModel

from revu.application.config import get_settings
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class OpenAIAdapter:
    def __init__(self, http_client: HttpClientGateway) -> None:
        self._http_client = http_client
        self._openai_client = AsyncClient(
            api_key=get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_API_KEY,  # type: ignore
            http_client=self._http_client.get_client(),
        )
        self.model = get_settings().AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL  # type: ignore

    async def get_chat_response(
        self,
        instructions: str,
        user_input: str,
        response_model: type[BaseModel] | None = None,
    ) -> ParsedResponse:
        """Call the Responses API, optionally constraining the answer to a schema.

        ``text_format`` must be omitted rather than passed as ``None``: the SDK
        treats ``None`` as a given value and fails with
        ``TypeError: Unsupported response_format type - None``. Without it no
        ``text`` parameter is sent at all, so callers that need structured
        output must pass ``response_model``, and callers in comment mode must
        read ``output_text`` instead of ``output_parsed``.
        """
        kwargs: dict[str, Any] = {"text_format": response_model} if response_model is not None else {}

        response = await self._openai_client.responses.parse(
            model=self.model,  # type: ignore
            instructions=instructions,
            input=user_input,
            **kwargs,
        )

        return response
