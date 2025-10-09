from unittest.mock import ANY, AsyncMock

from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)
from revu.infrastructure.http_client.http_client_gateway import get_http_gateway


async def test_openai_adapter_returns_sdk_response():
    fake_response = AsyncMock()

    adapter = OpenAICompatibleAdapter(http_client=get_http_gateway())
    adapter._openai_client = AsyncMock()
    adapter._openai_client.chat.completions.parse.return_value = fake_response
    adapter.model = "gpt-4o"

    messages = [
        ChatCompletionSystemMessageParam(role="system", content="system_prompt"),
        ChatCompletionUserMessageParam(role="user", content="user_prompt"),
    ]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp is fake_response
    adapter._openai_client.chat.completions.parse.assert_awaited_once_with(
        model=adapter.model, messages=messages, response_format=ANY
    )
