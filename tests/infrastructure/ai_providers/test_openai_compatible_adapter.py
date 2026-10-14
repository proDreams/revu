from unittest.mock import ANY, AsyncMock

from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)
from tests.conftest import make_ai_profile


def _profile():
    return make_ai_profile(
        name="cheap",
        vendor=AIProviderEnum.OPENAI_COMPATIBLE,
        base_url="https://cheap.example.com/v1",
        model="qwen",
    )


async def test_openai_compatible_adapter_returns_sdk_response(http_gateway):
    fake_response = AsyncMock()

    adapter = OpenAICompatibleAdapter(http_client=http_gateway, profile=_profile())
    adapter._openai_client = AsyncMock()
    adapter._openai_client.chat.completions.parse.return_value = fake_response

    messages = [
        ChatCompletionSystemMessageParam(role="system", content="system_prompt"),
        ChatCompletionUserMessageParam(role="user", content="user_prompt"),
    ]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp is fake_response
    assert adapter.model == "qwen"
    adapter._openai_client.chat.completions.parse.assert_awaited_once_with(
        model="qwen", messages=messages, response_format=ANY
    )
