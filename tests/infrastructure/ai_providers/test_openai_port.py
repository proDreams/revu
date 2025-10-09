from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GiteaReviewComment,
    GiteaReviewResponse,
    GitHubReviewComment,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(
        output_parsed="test output",
    )
    port = OpenAIPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"

    result = await port.get_comment_response(diff=diff, pr_title=pr_title, pr_body=pr_body)

    assert result == "test output"


async def test_github_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[
            GitHubReviewComment(path="test path", position=0, body="test body"),
            GitHubReviewComment(path="test path", position=3, body="test body 2"),
        ],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "github"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == output_parsed.general_comment
    assert result.comments[1].body == output_parsed.comments[1].body


async def test_github_with_system_prompt_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[GitHubReviewComment(path="test path", position=0, body="test body")],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)
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
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "gitea"

    result = await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == output_parsed.general_comment
    assert result.comments[0].body == output_parsed.comments[0].body


async def test_unknown_inline_response():
    adapter = AsyncMock()
    port = OpenAIPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"
    git_provider = "unknown"

    with pytest.raises(UnknownGitProvider) as exc_info:
        await port.get_inline_response(diff=diff, pr_title=pr_title, pr_body=pr_body, git_provider=git_provider)

    assert "unknown git provider" in str(exc_info.value)
