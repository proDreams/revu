from unittest.mock import AsyncMock

from pydantic import BaseModel

from revu.infrastructure.ai_providers.openai.openai_adapter import OpenAIAdapter


async def test_adapter_omits_text_format_when_no_model_is_requested(http_gateway, ai_profile):
    """Passing ``text_format=None`` to the SDK raises TypeError, so it must be omitted."""
    fake_response = AsyncMock()

    adapter = OpenAIAdapter(http_client=http_gateway, profile=ai_profile)
    adapter._openai_client = AsyncMock()
    adapter._openai_client.responses.parse.return_value = fake_response

    resp = await adapter.get_chat_response(instructions="instr", user_input="text")

    assert resp is fake_response
    assert adapter.model == ai_profile.model
    adapter._openai_client.responses.parse.assert_awaited_once_with(
        model=ai_profile.model, instructions="instr", input="text"
    )


async def test_adapter_passes_text_format_when_a_model_is_requested(http_gateway, ai_profile):
    class FakeModel(BaseModel):
        answer: str

    adapter = OpenAIAdapter(http_client=http_gateway, profile=ai_profile)
    adapter._openai_client = AsyncMock()

    await adapter.get_chat_response(instructions="instr", user_input="text", response_model=FakeModel)

    adapter._openai_client.responses.parse.assert_awaited_once_with(
        model=ai_profile.model, instructions="instr", input="text", text_format=FakeModel
    )
