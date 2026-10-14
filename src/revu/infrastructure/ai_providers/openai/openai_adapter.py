from typing import Any

from openai import AsyncClient
from openai.types.responses import ParsedResponse
from pydantic import BaseModel

from revu.application.entities.config import AIProfileConfig
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class OpenAIAdapter:
    def __init__(self, http_client: HttpClientGateway, profile: AIProfileConfig) -> None:
        self._http_client = http_client
        self.profile = profile
        self._openai_client = AsyncClient(
            api_key=profile.api_key,
            # The SDK is typed against its own httpx build, which is not the
            # one we depend on; the boundary tests drive the real client through
            # our transport, so the mismatch is in the stubs, not at runtime.
            http_client=self._http_client.get_client(),  # type: ignore[arg-type]
        )
        self.model = profile.model

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
