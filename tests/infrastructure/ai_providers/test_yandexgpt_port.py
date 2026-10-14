from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import InvalidAIOutput
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from tests.conftest import make_task
from tests.fixtures.infrastructure_responses.ai_responses import (
    AI_RESPONSE_JSON_ARRAY,
    INCOMPLETE_AI_RESPONSE_JSON,
    MISSING_GENERAL_COMMENT_AI_RESPONSE_JSON,
    VALID_BITBUCKET_AI_RESPONSE_JSON,
    VALID_GITEA_AI_RESPONSE_JSON,
    VALID_GITEA_MARKDOWN_AI_RESPONSE_JSON,
    VALID_GITHUB_AI_RESPONSE_JSON,
    VALID_GITHUB_AI_RESPONSE_JSON_LOWERCASE_SIDE,
)

pytestmark = pytest.mark.unit


def _port(output: str) -> YandexGPTPort:
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = output
    return YandexGPTPort(adapter=adapter)


def test_get_messages():
    messages = YandexGPTPort(adapter=AsyncMock())._get_messages(
        system_prompt="system prompt", user_prompt="user prompt"
    )

    assert isinstance(messages, list)
    assert messages[0]["text"] == "system prompt"


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = "test output"

    assert await YandexGPTPort(adapter=adapter).get_comment_response(make_task()) == "test output"


async def test_github_inline_response():
    result = await _port(VALID_GITHUB_AI_RESPONSE_JSON).get_inline_response(make_task())

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"
    assert result.comments[1].side == "LEFT"


async def test_lowercase_side_is_normalised():
    result = await _port(VALID_GITHUB_AI_RESPONSE_JSON_LOWERCASE_SIDE).get_inline_response(make_task())

    assert result.comments[0].side == "LEFT"


async def test_bitbucket_inline_response():
    result = await _port(VALID_BITBUCKET_AI_RESPONSE_JSON).get_inline_response(
        make_task(git_host=GitProviderEnum.BITBUCKET)
    )

    assert result.comments[0].lineType == "ADDED"
    assert result.comments[1].line == 5


async def test_the_task_system_prompt_is_used():
    port = _port(VALID_GITHUB_AI_RESPONSE_JSON)

    await port.get_inline_response(make_task(system_prompt="test system-prompt"))

    messages = port.adapter.get_chat_response.await_args.kwargs["messages"]
    assert messages[0]["text"].startswith("test system-prompt\n\n")


async def test_gitea_inline_response():
    result = await _port(VALID_GITEA_AI_RESPONSE_JSON).get_inline_response(make_task(git_host=GitProviderEnum.GITEA))

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_gitea_markdown_inline_response():
    result = await _port(VALID_GITEA_MARKDOWN_AI_RESPONSE_JSON).get_inline_response(
        make_task(git_host=GitProviderEnum.GITEA)
    )

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_invalid_inline_response():
    with pytest.raises(InvalidAIOutput) as exc_info:
        await _port("invalid response").get_inline_response(make_task(git_host=GitProviderEnum.GITEA))

    assert "invalid JSON response from yandexgpt" in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [INCOMPLETE_AI_RESPONSE_JSON, MISSING_GENERAL_COMMENT_AI_RESPONSE_JSON, AI_RESPONSE_JSON_ARRAY],
)
async def test_response_that_does_not_match_the_schema(payload):
    """Valid JSON with the wrong shape must fail as InvalidAIOutput, not KeyError."""
    with pytest.raises(InvalidAIOutput):
        await _port(payload).get_inline_response(make_task())
