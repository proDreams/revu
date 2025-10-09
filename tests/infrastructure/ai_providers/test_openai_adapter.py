from unittest.mock import AsyncMock

from revu.infrastructure.ai_providers.openai.openai_adapter import OpenAIAdapter
from revu.infrastructure.http_client.http_client_gateway import get_http_gateway


async def test_openai_adapter_returns_sdk_response():
    fake_response = AsyncMock()

    adapter = OpenAIAdapter(http_client=get_http_gateway())
    adapter._openai_client = AsyncMock()
    adapter._openai_client.responses.parse.return_value = fake_response
    adapter.model = "gpt-4o"

    resp = await adapter.get_chat_response(instructions="instr", user_input="text")

    assert resp is fake_response
    adapter._openai_client.responses.parse.assert_awaited_once_with(
        model=adapter.model, instructions="instr", input="text", text_format=None
    )
