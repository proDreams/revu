from unittest.mock import AsyncMock

import pytest
from gigachat.models import Chat

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    UnknownGitProvider,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.gigachat.gigachat_port import GigaChatPort
from tests.fixtures.infrastructure_responses.ai_responses import (
    AI_RESPONSE_JSON_ARRAY,
    INCOMPLETE_AI_RESPONSE_JSON,
    MISSING_GENERAL_COMMENT_AI_RESPONSE_JSON,
    VALID_BITBUCKET_AI_RESPONSE_JSON,
    VALID_GITEA_AI_RESPONSE_JSON,
    VALID_GITHUB_AI_RESPONSE_JSON,
    VALID_GITHUB_AI_RESPONSE_JSON_LOWERCASE_SIDE,
)


def _port(output: str) -> GigaChatPort:
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = output
    return GigaChatPort(adapter=adapter)


def test_get_chat():
    port = GigaChatPort(adapter=AsyncMock())

    system_prompt = "system prompt"
    user_prompt = "user prompt"

    chat = port._get_chat(system_prompt=system_prompt, user_prompt=user_prompt)

    assert isinstance(chat, Chat)


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = "test output"

    port = GigaChatPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"

    result = await port.get_comment_response(diff=diff, pr_title=pr_title, pr_body=pr_body)

    assert result == "test output"


async def test_github_inline_response():
    port = _port(VALID_GITHUB_AI_RESPONSE_JSON)

    result = await port.get_inline_response(
        diff="test diff", pr_title="test pr title", pr_body="test pr body", git_provider="github"
    )

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"
    assert result.comments[1].side == "LEFT"


async def test_lowercase_side_is_normalised():
    port = _port(VALID_GITHUB_AI_RESPONSE_JSON_LOWERCASE_SIDE)

    result = await port.get_inline_response(diff="d", pr_title="t", git_provider="github")

    assert result.comments[0].side == "LEFT"


async def test_bitbucket_inline_response():
    port = _port(VALID_BITBUCKET_AI_RESPONSE_JSON)

    result = await port.get_inline_response(diff="d", pr_title="t", git_provider="bitbucket")

    assert result.comments[0].lineType == "ADDED"
    assert result.comments[1].line == 5


async def test_github_with_system_prompt_inline_response():
    port = _port(VALID_GITHUB_AI_RESPONSE_JSON)
    port.system_prompt = "test system-prompt"

    result = await port.get_inline_response(
        diff="test diff", pr_title="test pr title", pr_body="test pr body", git_provider="github"
    )

    assert isinstance(result, ReviewResponseDTO)


async def test_gitea_inline_response():
    port = _port(VALID_GITEA_AI_RESPONSE_JSON)

    result = await port.get_inline_response(
        diff="test diff", pr_title="test pr title", pr_body="test pr body", git_provider="gitea"
    )

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_markdown_fenced_response_is_acccepted():
    port = _port(f"```json\n{VALID_GITEA_AI_RESPONSE_JSON}\n```")

    result = await port.get_inline_response(diff="d", pr_title="t", git_provider="gitea")

    assert isinstance(result, ReviewResponseDTO)


async def test_invalid_inline_response():
    port = _port("invalid response")

    with pytest.raises(InvalidAIOutput) as exc_info:
        await port.get_inline_response(diff="d", pr_title="t", pr_body="b", git_provider="gitea")

    assert "invalid JSON response from gigachat" in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [INCOMPLETE_AI_RESPONSE_JSON, MISSING_GENERAL_COMMENT_AI_RESPONSE_JSON, AI_RESPONSE_JSON_ARRAY],
)
async def test_response_that_does_not_match_the_schema(payload):
    """Valid JSON with the wrong shape must fail as InvalidAIOutput, not KeyError."""
    port = _port(payload)

    with pytest.raises(InvalidAIOutput):
        await port.get_inline_response(diff="d", pr_title="t", pr_body="b", git_provider="github")


async def test_unknown_inline_response():
    port = GigaChatPort(adapter=AsyncMock())

    with pytest.raises(UnknownGitProvider) as exc_info:
        await port.get_inline_response(diff="d", pr_title="t", pr_body="b", git_provider="unknown")

    assert "unknown git provider" in str(exc_info.value)
