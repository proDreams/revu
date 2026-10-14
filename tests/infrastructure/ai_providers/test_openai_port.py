from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
    UnknownGitProvider,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    BitbucketReviewComment,
    BitbucketReviewResponse,
    GiteaReviewComment,
    GiteaReviewResponse,
    GitHubReviewComment,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import (
    BitBucketReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort


async def test_comment_response_reads_output_text():
    """Comment mode requests no schema, so parsed output stays None."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(
        output_parsed=None,
        output_text="test output",
    )
    port = OpenAIPort(adapter=adapter)

    diff = "test diff"
    pr_title = "test pr title"
    pr_body = "test pr body"

    result = await port.get_comment_response(diff=diff, pr_title=pr_title, pr_body=pr_body)

    assert result == "test output"


async def test_comment_response_rejects_an_empty_answer():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="")
    port = OpenAIPort(adapter=adapter)

    with pytest.raises(NoAIResponse):
        await port.get_comment_response(diff="d", pr_title="t")


async def test_inline_response_rejects_a_missing_parsed_payload():
    """A refusal used to surface as AttributeError inside a background task."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None)
    port = OpenAIPort(adapter=adapter)

    with pytest.raises(InvalidAIOutput):
        await port.get_inline_response(diff="d", git_provider="github", pr_title="t")


async def test_github_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[
            GitHubReviewComment(path="test path", line=1, side="RIGHT", body="test body"),
            GitHubReviewComment(path="test path", line=3, side="LEFT", body="test body 2"),
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
    assert result.comments[1].side == "LEFT"
    assert result.comments[0].line == 1


async def test_github_with_system_prompt_inline_response():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[GitHubReviewComment(path="test path", line=1, body="test body")],
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

    # SYSTEM_PROMPT must extend the built-in prompt instead of replacing it,
    # otherwise the JSON contract providers rely on disappears.
    instructions = adapter.get_chat_response.await_args.kwargs["instructions"]
    assert instructions.startswith("test system-prompt\n\n")
    assert "general_comment" in instructions


async def test_github_with_system_prompt_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="output")
    port = OpenAIPort(adapter=adapter)
    port.system_prompt = "test system-prompt"

    await port.get_comment_response(diff="d", pr_title="t")

    instructions = adapter.get_chat_response.await_args.kwargs["instructions"]
    assert instructions.startswith("test system-prompt\n\n")
    assert instructions != "test system-prompt"


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


async def test_bitbucket_inline_response():
    output_parsed = BitbucketReviewResponse(
        general_comment="test comment",
        comments=[BitbucketReviewComment(path="test path", line=42, body="test body", lineType="ADDED")],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)

    result = await port.get_inline_response(diff="d", git_provider="bitbucket", pr_title="t", pr_body="b")

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"

    comment = result.comments[0]
    assert isinstance(comment, BitBucketReviewCommentDTO)
    assert comment.lineType == "ADDED"
    assert comment.line == 42
