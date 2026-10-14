from unittest.mock import AsyncMock, MagicMock

import pytest

from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.exceptions.ai_adapters_exceptions import NoAIResponse
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
    TextMessage,
    YandexGPTAdapter,
)
from tests.conftest import make_ai_profile

pytestmark = pytest.mark.unit


def _profile():
    return make_ai_profile(
        name="yandex",
        vendor=AIProviderEnum.YANDEXGPT,
        model="yandexgpt-lite",
        folder_id="test-folder-id",
    )


def _client(run_result):
    """Mirror the SDK: `completions()` is a synchronous factory, `run()` is async."""
    model = MagicMock()
    model.run = AsyncMock(return_value=run_result)
    client = MagicMock()
    client.models.completions.return_value = model

    return client, model


async def test_yandexgpt_adapter_returns_sdk_response():
    client, model = _client([MagicMock(text="test")])

    adapter = YandexGPTAdapter(profile=_profile())
    adapter._yandexgpt_client = client

    messages = [TextMessage(role="system", text="system_prompt")]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp == "test"
    # Creating the model is synchronous in this SDK; awaiting it raised TypeError.
    client.models.completions.assert_called_once_with("yandexgpt-lite")
    model.run.assert_awaited_once_with(messages)


@pytest.mark.parametrize("sdk_response", [None, [MagicMock(text="")]])
async def test_yandexgpt_adapter_reports_an_empty_response(sdk_response):
    client, _ = _client(sdk_response)

    adapter = YandexGPTAdapter(profile=_profile())
    adapter._yandexgpt_client = client

    messages = [TextMessage(role="system", text="system_prompt")]

    with pytest.raises(NoAIResponse) as exc_info:
        await adapter.get_chat_response(messages=messages)

    assert "Yandex GPT returned no response" in str(exc_info.value)
