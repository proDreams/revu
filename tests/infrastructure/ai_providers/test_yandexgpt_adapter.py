from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import NoAIResponse
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
    YandexGPTAdapter,
)


async def test_yandexgpt_adapter_returns_sdk_response(settings, monkeypatch):
    model_mock = AsyncMock()
    model_mock.run.return_value = [AsyncMock(text="test")]

    adapter = YandexGPTAdapter()
    adapter._yandexgpt_client = AsyncMock()
    adapter._yandexgpt_client.models.completions.return_value = model_mock

    messages = [{"role": "system", "text": "system_prompt"}, {"role": "user", "text": "user_prompt"}]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp == "test"
    adapter._yandexgpt_client.models.completions.assert_awaited_once_with(settings.AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL)
    model_mock.run.assert_awaited_once_with(messages)


async def test_yandexgpt_adapter_returns_empty_response(settings, monkeypatch):
    model_mock = AsyncMock()
    model_mock.run.return_value = None

    adapter = YandexGPTAdapter()
    adapter._yandexgpt_client = AsyncMock()
    adapter._yandexgpt_client.models.completions.return_value = model_mock

    messages = [{"role": "system", "text": "system_prompt"}, {"role": "user", "text": "user_prompt"}]

    with pytest.raises(NoAIResponse) as exc_info:
        await adapter.get_chat_response(messages=messages)

    assert "Yandex GPT returned no response" in str(exc_info.value)
