from unittest.mock import AsyncMock, MagicMock

from gigachat.models import Chat, Messages, MessagesRole

from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import GigaChatAdapter
from tests.conftest import make_ai_profile


def _profile():
    return make_ai_profile(
        name="giga",
        vendor=AIProviderEnum.GIGACHAT,
        model="GigaChat",
        scope="GIGACHAT_API_PERS",
    )


async def test_gigachat_adapter_returns_sdk_response():
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="test"))]

    adapter = GigaChatAdapter(profile=_profile())
    adapter._gigachat_client = AsyncMock()
    adapter._gigachat_client.achat.return_value = fake_response

    payload = Chat(
        messages=[
            Messages(role=MessagesRole.SYSTEM, content="system_prompt"),
            Messages(role=MessagesRole.USER, content="user_prompt"),
        ]
    )

    resp = await adapter.get_chat_response(payload=payload)

    assert resp == "test"
    adapter._gigachat_client.achat.assert_awaited_once_with(payload=payload)


async def test_gigachat_adapter_closes_its_client():
    """The SDK owns its transport, so the registry must be able to close it."""
    adapter = GigaChatAdapter(profile=_profile())
    adapter._gigachat_client = AsyncMock()

    await adapter.aclose()

    adapter._gigachat_client.aclose.assert_awaited_once()
