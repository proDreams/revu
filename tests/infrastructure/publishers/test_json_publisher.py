"""A review as data, for whatever reads a pipeline's output."""

import io
import json

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GitHubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.publishers.json_publisher import JsonPublisher

pytestmark = pytest.mark.unit


@pytest.fixture
def output():
    return io.StringIO()


@pytest.fixture
def publisher(output):
    return JsonPublisher(stream=output)


async def test_a_comment_becomes_one_object(publisher, output):
    await publisher.send_comment(repo_owner="owner/repo", review="итог", index=7)

    assert json.loads(output.getvalue()) == {
        "kind": "comment",
        "repo": "owner/repo",
        "number": 7,
        "body": "итог",
    }


async def test_an_inline_review_keeps_every_field_of_every_comment(publisher, output):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=ReviewResponseDTO(
            general_comment="итог",
            comments=[GitHubReviewCommentDTO(path="a.py", line=4, side="RIGHT", body="тут")],
        ),
        index=7,
    )

    payload = json.loads(output.getvalue())
    assert (payload["kind"], payload["sha"], payload["summary"]) == ("inline", "abc", "итог")
    assert payload["comments"] == [{"path": "a.py", "line": 4, "body": "тут", "side": "RIGHT"}]


async def test_a_comment_that_is_not_a_dataclass_still_reports_its_text(publisher, output):
    class Odd:
        body = "тело"

    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=ReviewResponseDTO(general_comment="итог", comments=[Odd()]),  # type: ignore[list-item]
        index=7,
    )

    assert json.loads(output.getvalue())["comments"] == [{"body": "тело"}]


async def test_non_ascii_is_not_escaped(capsys):
    """A review in Russian stays readable in the log it is printed to."""
    await JsonPublisher().send_comment(repo_owner="owner/repo", review="привет", index=1)

    assert "привет" in capsys.readouterr().out


async def test_the_default_destination_is_stdout(capsys):
    await JsonPublisher().send_comment(repo_owner="owner/repo", review="итог", index=1)

    assert json.loads(capsys.readouterr().out)["body"] == "итог"
