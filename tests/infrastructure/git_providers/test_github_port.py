from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GitHubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.git_providers.github.github_port import GithubPort
from tests.conftest import GITHUB_TOKEN, make_connection

pytestmark = pytest.mark.unit


def _port(http_client: AsyncMock, **connection) -> GithubPort:
    return GithubPort(http_client=http_client, config=make_connection(**connection))


def test_get_headers():
    headers = _port(AsyncMock())._get_headers()

    assert headers == {"Authorization": f"token {GITHUB_TOKEN}"}


def test_defaults_to_github_com():
    """github.com is used when no self-hosted base URL is configured."""
    assert _port(AsyncMock(), base_url=None)._url("repos/o/r") == "https://api.github.com/repos/o/r"


def test_github_enterprise_base_url():
    port = _port(AsyncMock(), base_url="https://ghe.example.com/api/v3")

    assert port._url("repos/o/r/pulls/1.diff") == "https://ghe.example.com/api/v3/repos/o/r/pulls/1.diff"


async def test_fetch_diff_decodes_bytes_to_str():
    """The gateway returns raw bytes; the port owes the protocol a str diff."""
    http_client = AsyncMock()
    http_client.get.return_value = b"test diff"

    port = _port(http_client, base_url="https://ghe.example.com/api/v3")

    result = await port.fetch_diff(repo="test", index=1)

    assert result == "test diff"
    assert isinstance(result, str)
    assert http_client.get.await_args.kwargs["url"] == "https://ghe.example.com/api/v3/repos/test/pulls/1.diff"
    assert http_client.get.await_args.kwargs["expect_json"] is False


async def test_send_comment():
    http_client = AsyncMock(post=AsyncMock())

    await _port(http_client).send_comment(repo_owner="test", review="test review", index=1)

    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"body": "test review"})


async def test_send_inline_sends_line_and_side():
    """GitHub anchors inline comments by line + side, not by the deprecated position."""
    http_client = AsyncMock(post=AsyncMock())
    port = _port(http_client)

    review = ReviewResponseDTO(
        general_comment="test review",
        comments=[
            GitHubReviewCommentDTO(path="app.py", line=10, side="RIGHT", body="first"),
            GitHubReviewCommentDTO(path="app.py", line=4, side="LEFT", body="second"),
        ],
    )

    await port.send_inline(sha="test sha", repo_owner="test", review=review, index=1)

    payload = http_client.post.await_args.kwargs["payload"]
    assert payload["commit_id"] == "test sha"
    assert payload["body"] == "test review"
    assert payload["comments"] == [asdict(comment) for comment in review.comments]
    assert payload["comments"][0] == {"path": "app.py", "line": 10, "body": "first", "side": "RIGHT"}
    assert "position" not in payload["comments"][0]
