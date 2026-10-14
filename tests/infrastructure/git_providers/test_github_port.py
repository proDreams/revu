from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GithubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.git_providers.github.github_port import GithubPort

pytestmark = pytest.mark.unit


def test_get_headers(settings):
    port = GithubPort(http_client=AsyncMock())

    headers = port._get_headers()

    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"token {settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN}"


def test_defaults_to_github_com(settings):
    """github.com is used when no self-hosted base URL is configured."""
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_URL"] = None

    port = GithubPort(http_client=AsyncMock())

    assert port._url("repos/o/r") == "https://api.github.com/repos/o/r"


async def test_fetch_diff_decodes_bytes_to_str(settings):
    """The gateway returns raw bytes; the port owes the protocol a str diff."""
    http_client = AsyncMock()
    http_client.get.return_value = b"test diff"

    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_URL"] = "https://ghe.example.com/api/v3"
    port = GithubPort(http_client=http_client)

    result = await port.fetch_diff(repo="test", index=1)

    assert result == "test diff"
    assert isinstance(result, str)
    assert http_client.get.await_args.kwargs["url"] == "https://ghe.example.com/api/v3/repos/test/pulls/1.diff"
    assert http_client.get.await_args.kwargs["expect_json"] is False


def test_github_enterprise_base_url(settings):
    settings["GIT_PROVIDER_CONFIG"]["GIT_PROVIDER_URL"] = "https://ghe.example.com/api/v3"

    port = GithubPort(http_client=AsyncMock())

    assert port._url("repos/o/r/pulls/1.diff") == "https://ghe.example.com/api/v3/repos/o/r/pulls/1.diff"


async def test_send_comment(settings):
    http_client = AsyncMock(post=AsyncMock())
    port = GithubPort(http_client=http_client)

    repo_owner = "test"
    review = "test review"
    index = 1

    await port.send_comment(repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"body": review})


async def test_send_inline_sends_line_and_side():
    """GitHub anchors inline comments by line + side, not by the deprecated position."""
    http_client = AsyncMock(post=AsyncMock())
    port = GithubPort(http_client=http_client)

    sha = "test sha"
    repo_owner = "test"
    review = ReviewResponseDTO(
        general_comment="test review",
        comments=[
            GithubReviewCommentDTO(path="app.py", line=10, side="RIGHT", body="first"),
            GithubReviewCommentDTO(path="app.py", line=4, side="LEFT", body="second"),
        ],
    )
    index = 1

    payload = {
        "commit_id": sha,
        "body": review.general_comment,
        "comments": [asdict(comment) for comment in review.comments],
    }

    await port.send_inline(sha=sha, repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload=payload)

    sent_comments = http_client.post.await_args.kwargs["payload"]["comments"]
    assert sent_comments == [
        {"path": "app.py", "line": 10, "body": "first", "side": "RIGHT"},
        {"path": "app.py", "line": 4, "body": "second", "side": "LEFT"},
    ]
    assert "position" not in sent_comments[0]
