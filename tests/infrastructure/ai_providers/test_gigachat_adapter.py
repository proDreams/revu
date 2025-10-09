from unittest.mock import AsyncMock, MagicMock

from gigachat.models import Chat, Messages, MessagesRole

from revu.infrastructure.ai_providers.gigachat.gigachat_adapter import GigaChatAdapter


async def test_gigachat_adapter_returns_sdk_response(settings, monkeypatch):
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(content="test"))]

    adapter = GigaChatAdapter()
    adapter._gigachat_client = AsyncMock()
    adapter._gigachat_client.chat.return_value = fake_response

    payload = Chat(
        messages=[
            Messages(role=MessagesRole.SYSTEM, content="system_prompt"),
            Messages(role=MessagesRole.USER, content="user_prompt"),
        ]
    )

    resp = await adapter.get_chat_response(payload=payload)

    assert resp == "test"
    adapter._gigachat_client.chat.assert_awaited_once_with(payload=payload)
