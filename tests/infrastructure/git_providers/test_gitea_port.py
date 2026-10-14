from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from tests.conftest import GITEA_TOKEN, GITEA_URL, make_connection

pytestmark = pytest.mark.unit


def _port(http_client: AsyncMock, **connection) -> GiteaPort:
    config = make_connection(
        key="gitea-int",
        host=GitProviderEnum.GITEA,
        user_token=GITEA_TOKEN,
        base_url=GITEA_URL,
        **connection,
    )

    return GiteaPort(http_client=http_client, config=config)


def test_get_headers():
    headers = _port(AsyncMock())._get_headers()

    assert headers == {"Authorization": f"token {GITEA_TOKEN}"}


async def test_fetch_diff_decodes_bytes_to_str():
    """The gateway returns raw bytes; the port owes the protocol a str diff."""
    http_client = AsyncMock()
    http_client.get.return_value = b"test diff"

    result = await _port(http_client).fetch_diff(repo="test", index=1)

    assert result == "test diff"
    assert isinstance(result, str)
    assert http_client.get.await_args.kwargs["url"] == f"{GITEA_URL}/api/v1/repos/test/pulls/1.diff"
    assert http_client.get.await_args.kwargs["expect_json"] is False


async def test_send_comment():
    http_client = AsyncMock(post=AsyncMock())

    await _port(http_client).send_comment(repo_owner="test", review="test review", index=1)

    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"body": "test review"})


async def test_send_inline():
    http_client = AsyncMock(post=AsyncMock())
    review = ReviewResponseDTO(
        general_comment="test review",
        comments=[GiteaReviewCommentDTO(path="test", old_position=1, new_position=0, body="test body")],
    )

    await _port(http_client).send_inline(sha="test sha", repo_owner="test", review=review, index=1)

    payload = {
        "commit_id": "test sha",
        "body": review.general_comment,
        "comments": [asdict(comment) for comment in review.comments],
    }
    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload=payload)


BOT = {"login": "revu-bot"}


async def test_fetch_review_context_uses_the_gitea_api_prefix():
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [], [], []]

    await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    urls = [call.kwargs["url"] for call in http_client.get.await_args_list]
    assert urls[0] == "https://gitea.internal/api/v1/user"
    assert all("api/v1/repos/owner/repo/" in url for url in urls[1:])


async def test_fetch_review_context_marks_revu_comments():
    ours = {"user": BOT, "body": "поправь", "path": "app.py", "line": 3, "created_at": "2026-01-02T00:00:00Z"}
    theirs = {"user": {"login": "ivan"}, "body": "ок", "created_at": "2026-01-01T00:00:00Z"}
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [theirs], [ours], []]

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert [comment.is_revu for comment in context.comments] == [False, True]
