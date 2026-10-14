from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    BitbucketReviewComment,
    BitbucketReviewResponse,
    GiteaReviewComment,
    GiteaReviewResponse,
    GitHubReviewComment,
    GithubReviewResponse,
    GitLabReviewComment,
    PreviousFinding,
)
from revu.domain.entities.dto.ai_provider_dto import (
    BitbucketReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from tests.conftest import make_task

pytestmark = pytest.mark.unit


async def test_comment_response_reads_output_text():
    """Comment mode requests no schema, so parsed output stays None."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="test output")
    port = OpenAIPort(adapter=adapter)

    assert await port.get_comment_response(make_task()) == "test output"


async def test_comment_response_rejects_an_empty_answer():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="")

    with pytest.raises(NoAIResponse):
        await OpenAIPort(adapter=adapter).get_comment_response(make_task())


async def test_inline_response_rejects_a_missing_parsed_payload():
    """A refusal used to surface as AttributeError inside a background task."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None)

    with pytest.raises(InvalidAIOutput):
        await OpenAIPort(adapter=adapter).get_inline_response(make_task())


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

    result = await port.get_inline_response(make_task())

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"
    assert result.comments[1].side == "LEFT"
    assert result.comments[0].line == 1


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

    result = await port.get_inline_response(make_task(git_host=GitProviderEnum.GITEA))

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[0].body == "test body"


async def test_bitbucket_inline_response():
    output_parsed = BitbucketReviewResponse(
        general_comment="test comment",
        comments=[BitbucketReviewComment(path="test path", line=42, body="test body", lineType="ADDED")],
    )

    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)

    result = await port.get_inline_response(make_task(git_host=GitProviderEnum.BITBUCKET))

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"

    comment = result.comments[0]
    assert isinstance(comment, BitbucketReviewCommentDTO)
    assert comment.lineType == "ADDED"
    assert comment.line == 42


async def test_the_task_system_prompt_is_prepended_to_the_inline_prompt():
    """SYSTEM_PROMPT must extend the built-in prompt instead of replacing it."""
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[GitHubReviewComment(path="test path", line=1, body="test body")],
    )
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=output_parsed)
    port = OpenAIPort(adapter=adapter)

    await port.get_inline_response(make_task(system_prompt="test system-prompt"))

    instructions = adapter.get_chat_response.await_args.kwargs["instructions"]
    assert instructions.startswith("test system-prompt\n\n")
    assert "general_comment" in instructions


async def test_the_task_system_prompt_is_prepended_to_the_comment_prompt():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="output")
    port = OpenAIPort(adapter=adapter)

    await port.get_comment_response(make_task(system_prompt="test system-prompt"))

    instructions = adapter.get_chat_response.await_args.kwargs["instructions"]
    assert instructions.startswith("test system-prompt\n\n")
    assert instructions != "test system-prompt"


async def test_without_a_system_prompt_the_builtin_prompt_is_used():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = AsyncMock(output_parsed=None, output_text="output")
    port = OpenAIPort(adapter=adapter)

    await port.get_comment_response(make_task(system_prompt=None))

    instructions = adapter.get_chat_response.await_args.kwargs["instructions"]
    assert instructions.lstrip().startswith("Ты — опытный инженер-программист")
    assert "Ты — опытный инженер-программист" in instructions


def test_a_gitlab_comment_needs_a_line():
    """A GitLab note with neither side cannot be positioned at all."""
    with pytest.raises(ValidationError):
        GitLabReviewComment(path="app.py", body="nowhere")


def test_a_gitlab_comment_treats_a_blank_line_as_absent():
    """Providers without a schema often answer an inapplicable line as ""."""
    comment = GitLabReviewComment(path="app.py", body="b", new_line="", old_line="5")

    assert comment.new_line is None
    assert comment.old_line == 5


def test_a_gitlab_comment_accepts_both_sides():
    comment = GitLabReviewComment(path="app.py", body="b", new_line=7, old_line=6)

    assert (comment.old_line, comment.new_line) == (6, 7)


@pytest.mark.parametrize(
    ("raw_status", "expected"),
    [
        ("fixed", "fixed"),
        ("FIXED", "fixed"),
        ("исправлено", "fixed"),
        ("resolved", "fixed"),
        ("remaining", "remaining"),
        ("исправлю потом", "remaining"),
        (None, "remaining"),
    ],
)
def test_a_finding_status_is_normalised(raw_status, expected):
    """Models answer in their own words; only an explicit fix counts as one."""
    finding = PreviousFinding(summary="s", status=raw_status)

    assert finding.status.value == expected


def test_a_finding_defaults_to_remaining():
    assert PreviousFinding(summary="s").status.value == "remaining"


def test_a_review_response_carries_the_finding_statuses():
    response = GithubReviewResponse.model_validate(
        {
            "general_comment": "c",
            "previous_findings": [{"summary": "a", "status": "fixed"}],
            "comments": [],
        }
    )

    assert response.previous_findings[0].status.value == "fixed"


def test_a_review_response_without_findings_is_fine():
    response = GithubReviewResponse.model_validate({"general_comment": "c", "comments": []})

    assert response.previous_findings == []
