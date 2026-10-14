from unittest.mock import AsyncMock

import pytest

from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.exceptions.ai_adapters_exceptions import NoAIResponse
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_adapter import (
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


async def test_yandexgpt_adapter_returns_sdk_response():
    model_mock = AsyncMock()
    model_mock.run.return_value = [AsyncMock(text="test")]

    adapter = YandexGPTAdapter(profile=_profile())
    adapter._yandexgpt_client = AsyncMock()
    adapter._yandexgpt_client.models.completions.return_value = model_mock

    messages = [{"role": "system", "text": "system_prompt"}, {"role": "user", "text": "user_prompt"}]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp == "test"
    adapter._yandexgpt_client.models.completions.assert_awaited_once_with("yandexgpt-lite")
    model_mock.run.assert_awaited_once_with(messages)


@pytest.mark.parametrize("sdk_response", [None, [AsyncMock(text="")]])
async def test_yandexgpt_adapter_reports_an_empty_response(sdk_response):
    model_mock = AsyncMock()
    model_mock.run.return_value = sdk_response

    adapter = YandexGPTAdapter(profile=_profile())
    adapter._yandexgpt_client = AsyncMock()
    adapter._yandexgpt_client.models.completions.return_value = model_mock

    messages = [{"role": "system", "text": "system_prompt"}, {"role": "user", "text": "user_prompt"}]

    with pytest.raises(NoAIResponse) as exc_info:
        await adapter.get_chat_response(messages=messages)

    assert "Yandex GPT returned no response" in str(exc_info.value)
