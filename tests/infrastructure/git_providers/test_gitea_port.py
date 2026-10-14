from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort

pytestmark = pytest.mark.unit


def test_get_headers(settings):
    port = GiteaPort(http_client=AsyncMock())

    headers = port._get_headers()

    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"token {settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN}"


async def test_fetch_diff_decodes_bytes_to_str():
    """The gateway returns raw bytes; the port owes the protocol a str diff."""
    http_client = AsyncMock()
    http_client.get.return_value = b"test diff"
    port = GiteaPort(http_client=http_client)

    result = await port.fetch_diff(repo="test", index=1)

    assert result == "test diff"
    assert isinstance(result, str)
    assert http_client.get.await_args.kwargs["url"] == "https://example.com/api/v1/repos/test/pulls/1.diff"
    assert http_client.get.await_args.kwargs["expect_json"] is False


async def test_send_comment(settings):
    http_client = AsyncMock(post=AsyncMock())
    port = GiteaPort(http_client=http_client)

    repo_owner = "test"
    review = "test review"
    index = 1

    await port.send_comment(repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"body": review})


async def test_send_inline():
    http_client = AsyncMock(post=AsyncMock())
    port = GiteaPort(http_client=http_client)

    sha = "test sha"
    repo_owner = "test"
    review = ReviewResponseDTO(
        general_comment="test review",
        comments=[GiteaReviewCommentDTO(path="test", old_position=1, new_position=0, body="test body")],
    )
    index = 1

    payload = {
        "commit_id": sha,
        "body": review.general_comment,
        "comments": [asdict(comment) for comment in review.comments],
    }

    await port.send_inline(sha=sha, repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload=payload)
