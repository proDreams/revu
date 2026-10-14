from unittest.mock import AsyncMock, MagicMock

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
)
from revu.application.entities.schemas.ai_providers_schemas.openai_schemas import (
    GiteaReviewComment,
    GiteaReviewResponse,
    GitHubReviewComment,
    GithubReviewResponse,
)
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from tests.conftest import make_task

pytestmark = pytest.mark.unit


def _response(parsed=None, content=None):
    fake_response = MagicMock()
    fake_response.choices = [MagicMock(message=MagicMock(parsed=parsed, content=content))]
    return fake_response


def test_get_messages():
    messages = OpenAICompatiblePort(adapter=AsyncMock())._get_messages(
        system_prompt="system prompt", user_prompt="user prompt"
    )

    assert isinstance(messages, list)
    assert messages[0]["content"] == "system prompt"


async def test_comment_response():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(content="test")

    assert await OpenAICompatiblePort(adapter=adapter).get_comment_response(make_task()) == "test"


async def test_comment_response_rejects_an_empty_answer():
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(content=None)

    with pytest.raises(NoAIResponse):
        await OpenAICompatiblePort(adapter=adapter).get_comment_response(make_task())


async def test_inline_response_rejects_a_missing_parsed_payload():
    """A refusal used to surface as AttributeError inside a background task."""
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=None, content="I cannot help with that")

    with pytest.raises(InvalidAIOutput):
        await OpenAICompatiblePort(adapter=adapter).get_inline_response(make_task())


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

    result = await port.get_inline_response(make_task())

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"
    assert result.comments[1].side == "LEFT"


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

    result = await port.get_inline_response(make_task(git_host=GitProviderEnum.GITEA))

    assert isinstance(result, ReviewResponseDTO)
    assert result.general_comment == "test comment"
    assert result.comments[1].body == "test body 2"


async def test_the_task_system_prompt_reaches_the_system_message():
    output_parsed = GithubReviewResponse(
        general_comment="test comment",
        comments=[GitHubReviewComment(path="test path", line=1, body="test body")],
    )
    adapter = AsyncMock()
    adapter.get_chat_response.return_value = _response(parsed=output_parsed)
    port = OpenAICompatiblePort(adapter=adapter)

    await port.get_inline_response(make_task(system_prompt="test system-prompt"))

    messages = adapter.get_chat_response.await_args.kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("test system-prompt\n\n")
