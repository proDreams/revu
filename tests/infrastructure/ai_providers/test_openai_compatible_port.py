from unittest.mock import AsyncMock, MagicMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GiteaReviewComment,
    GiteaReviewResponse,
    GitHubReviewComment,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)


def _response(parsed=None, content=None):
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(parsed=parsed, content=content))]
    return fake_response


def test_get_messages():
    port = OpenAICompatiblePort(adapter=AsyncMock())

    system_prompt = "system prompt"
    user_prompt = "user prompt"

    messages = port._get_messages(system_prompt=system_prompt, user_prompt=user_prompt)

    assert isinstance(messages, list)
    assert messages[0]["content"] == system_prompt


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(content="test")

    port = OpenAICompatiblePort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"

    result = await port.get_comment_response(diff=diff, pr_title=pr_title, pr_body=pr_body)

    assert result == "test"


async def test_comment_response_rejects_an_empty_answer():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(content=None)

    port = OpenAICompatiblePort(adapter=adapter)

    with pytest.raises(NoAIResponse):
        await port.get_comment_response(diff="d", pr_title="t")


async def test_inline_response_rejects_a_missing_parsed_payload():
    """A refusal used to surface as AttributeError inside a background task."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=None, content="I cannot help with that")

    port = OpenAICompatiblePort(adapter=adapter)

    with pytest.raises(InvalidAIOutput):
        await port.get_inline_response(diff="d", pr_title="t", git_provider="github")


async def test_github_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[
            GitHubReviewComment(path="test path", line=1, side="RIGHT", body="test body"),
            GitHubReviewComment(path="test path", line=3, side="LEFT", body="test body 2"),
        ],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=output_parsed)

    port = OpenAICompatiblePort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "github"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"
    assert result.comments[1].side == "LEFT"


async def test_github_with_system_prompt_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[
            GitHubReviewComment(path="test path", line=1, body="test body"),
            GitHubReviewComment(path="test path", line=3, body="test body 2"),
        ],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=output_parsed)

    port = OpenAICompatiblePort(adapter=adapter)
    port.system_prompt = "test system-prompt"

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "github"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)


async def test_gitea_inline_response():
    output_parsed = GiteaReviewResponse(
        general_comment="test comment",
        comments=[
            GiteaReviewComment(path="test path", old_position=1, new_position=0, body="test body"),
            GiteaReviewComment(path="test path", old_position=0, new_position=3, body="test body 2"),
        ],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=output_parsed)

    port = OpenAICompatiblePort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "gitea"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_unknown_inline_response():
    adapter = AsyncMock()
    port = OpenAICompatiblePort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "unknown"

    with pytest.raises(UnknownGitProvider) as exc_info:
        await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert "unknown git provider" in str(exc_info.value)
