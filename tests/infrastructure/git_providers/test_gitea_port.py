from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.application.entities.review_marker import mark
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


REVU_BODY = mark("поправь")
OURS = {
    "user": {"login": "revu-bot"},
    "body": REVU_BODY,
    "path": "app.py",
    "line": 3,
    "created_at": "2026-01-02T00:00:00Z",
}
THEIRS = {"user": {"login": "revu-bot"}, "body": "моя же заметка", "created_at": "2026-01-01T00:00:00Z"}


async def test_fetch_review_context_uses_the_gitea_api_prefix():
    http_client = AsyncMock()
    http_client.get.side_effect = [[], []]

    await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    urls = [call.kwargs["url"] for call in http_client.get.await_args_list]
    assert all("api/v1/repos/owner/repo/" in url for url in urls)


async def test_fetch_review_context_never_asks_for_githubs_inline_route():
    """Gitea has no `/pulls/{index}/comments`: it answers 404, and the 404 used to
    cost the whole history — a repeated review never saw its own inline findings.

    Gitea's documented routes are the issue timeline (an inline review comment is
    an issue comment there) and `/pulls/{index}/reviews` for the review bodies.
    """
    http_client = AsyncMock()
    http_client.get.side_effect = [[], []]

    await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    urls = [call.kwargs["url"].split("?")[0] for call in http_client.get.await_args_list]
    assert urls == [
        f"{GITEA_URL}/api/v1/repos/owner/repo/issues/7/comments",
        f"{GITEA_URL}/api/v1/repos/owner/repo/pulls/7/reviews",
    ]


async def test_fetch_review_context_tells_its_own_comment_from_the_author_note():
    """Gitea shares the account with the author exactly like GitHub does."""
    http_client = AsyncMock()
    http_client.get.side_effect = [[THEIRS], [OURS]]

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert [comment.body for comment in context.findings] == ["поправь"]
    assert [comment.body for comment in context.discussion] == ["моя же заметка"]


async def test_fetch_file_uses_the_gitea_raw_endpoint():
    http_client = AsyncMock()
    http_client.get.return_value = b"text"

    await _port(http_client).fetch_file(repo="owner/repo", path="src/app.go", revision="abc")

    assert http_client.get.await_args.kwargs["url"] == (
        "https://gitea.internal/api/v1/repos/owner/repo/raw/src/app.go?ref=abc"
    )


async def test_list_files_uses_the_gitea_tree_endpoint():
    http_client = AsyncMock()
    http_client.get.return_value = {"tree": [{"path": "a.go", "type": "blob"}]}

    paths = await _port(http_client).list_files(repo="owner/repo", revision="abc")

    assert paths == ("a.go",)
    assert http_client.get.await_args.kwargs["url"] == (
        "https://gitea.internal/api/v1/repos/owner/repo/git/trees/abc?recursive=1"
    )
