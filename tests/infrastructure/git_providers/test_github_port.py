from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

from revu.domain.entities.dto.ai_provider_dto import (
    GithubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.git_providers.github.github_port import GithubPort


def test_get_headers(settings):
    port = GithubPort(http_client=AsyncMock())

    headers = port._get_headers()

    assert isinstance(headers, dict)
    assert headers["Authorization"] == f"token {settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN}"


async def test_fetch_diff():
    http_client = AsyncMock()
    http_client.get.return_value = "test diff"
    port = GithubPort(http_client=http_client)

    repo = "test"
    index = 1

    result = await port.fetch_diff(repo=repo, index=index)

    assert result == "test diff"


async def test_send_comment(settings):
    http_client = AsyncMock(post=AsyncMock())
    port = GithubPort(http_client=http_client)

    repo_owner = "test"
    review = "test review"
    index = 1

    await port.send_comment(repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"body": review})


async def test_send_inline():
    http_client = AsyncMock(post=AsyncMock())
    port = GithubPort(http_client=http_client)

    sha = "test sha"
    repo_owner = "test"
    review = ReviewResponseDTO(
        general_comment="test review",
        comments=[GithubReviewCommentDTO(path="test", position=0, body="test body")],
    )
    index = 1

    payload = {
        "commit_id": sha,
        "body": review.general_comment,
        "comments": [asdict(comment) for comment in review.comments],
    }

    await port.send_inline(sha=sha, repo_owner=repo_owner, review=review, index=index)
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload=payload)
