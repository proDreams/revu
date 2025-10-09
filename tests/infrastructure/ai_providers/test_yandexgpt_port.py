from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from tests.fixtures.infrastructure_responses.ai_responses import (
    VALID_GITEA_AI_RESPONSE_JSON,
    VALID_GITEA_MARKDOWN_AI_RESPONSE_JSON,
    VALID_GITHUB_AI_RESPONSE_JSON,
)


def test_get_messages():
    port = YandexGPTPort(adapter=AsyncMock())

    system_prompt = "system prompt"
    user_prompt = "user prompt"

    messages = port._get_messages(system_prompt=system_prompt, user_prompt=user_prompt)

    assert isinstance(messages, list)
    assert messages[0]["text"] == "system prompt"


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = "test output"

    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"

    result = await port.get_comment_response(diff=diff, pr_title=pr_title, pr_body=pr_body)

    assert result == "test output"


async def test_github_inline_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = VALID_GITHUB_AI_RESPONSE_JSON

    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "github"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_github_with_system_prompt_inline_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = VALID_GITHUB_AI_RESPONSE_JSON

    port = YandexGPTPort(adapter=adapter)
    port.system_prompt = "test system-prompt"

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "github"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)


async def test_gitea_inline_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = VALID_GITEA_AI_RESPONSE_JSON

    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "gitea"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_gitea_markdown_inline_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = VALID_GITEA_MARKDOWN_AI_RESPONSE_JSON

    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "gitea"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_invalid_inline_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = "invalid response"

    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "gitea"

    with pytest.raises(InvalidAIOutput) as exc_info:
        await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert "invalid JSON response from yandexgpt" in str(exc_info.value)


async def test_unknown_inline_response():
    adapter = AsyncMock()
    port = YandexGPTPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "unknown"

    with pytest.raises(UnknownGitProvider) as exc_info:
        await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert "unknown git provider" in str(exc_info.value)
