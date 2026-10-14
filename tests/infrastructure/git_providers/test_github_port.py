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


BOT = {"login": "revu-bot"}
ISSUE_COMMENT = {"user": {"login": "ivan"}, "body": "как дела?", "created_at": "2026-01-01T00:00:00Z"}
INLINE_COMMENT = {
    "user": BOT,
    "body": "импорты лучше построчно",
    "path": "app.py",
    "line": 12,
    "created_at": "2026-01-02T00:00:00Z",
}
REVIEW_BODY = {"user": BOT, "body": "итог ревью", "submitted_at": "2026-01-03T00:00:00Z"}


def _context_client() -> AsyncMock:
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [ISSUE_COMMENT], [INLINE_COMMENT], [REVIEW_BODY]]

    return http_client


async def test_fetch_review_context_reads_every_conversation():
    """A pull request keeps its timeline, its inline comments and its reviews apart."""
    http_client = _context_client()

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    urls = [call.kwargs["url"] for call in http_client.get.await_args_list]
    assert urls[0] == "https://api.github.com/user"
    assert "repos/owner/repo/issues/7/comments" in urls[1]
    assert "repos/owner/repo/pulls/7/comments" in urls[2]
    assert "repos/owner/repo/pulls/7/reviews" in urls[3]


async def test_fetch_review_context_marks_revu_comments_and_keeps_the_order():
    context = await _port(_context_client()).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert [comment.author for comment in context.comments] == ["ivan", "revu-bot", "revu-bot"]
    assert [comment.is_revu for comment in context.comments] == [False, True, True]
    assert [comment.body for comment in context.findings] == ["импорты лучше построчно", "итог ревью"]


async def test_fetch_review_context_keeps_the_place_of_an_inline_comment():
    context = await _port(_context_client()).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    finding = context.findings[0]
    assert (finding.path, finding.line) == ("app.py", 12)
    # GitHub has no resolution state over REST.
    assert finding.resolved is False


async def test_fetch_review_context_falls_back_to_the_original_line():
    """GitHub nulls `line` once the anchor moves out of the diff."""
    moved = {**INLINE_COMMENT, "line": None, "original_line": 44}
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [], [moved], []]

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert context.findings[0].line == 44


async def test_fetch_review_context_looks_the_bot_up_once():
    http_client = _context_client()
    port = _port(http_client)

    for _ in range(2):
        http_client.get.side_effect = [BOT, [ISSUE_COMMENT], [INLINE_COMMENT], [REVIEW_BODY]]
        await port.fetch_review_context(repo="owner/repo", index=7)

    logins = [call.kwargs["url"] for call in http_client.get.await_args_list if call.kwargs["url"].endswith("/user")]
    assert len(logins) == 1


async def test_fetch_review_context_skips_empty_bodies():
    """An approval or a label change carries no text worth showing."""
    empty = {"user": BOT, "body": "   ", "created_at": "2026-01-04T00:00:00Z"}
    missing = {"user": BOT, "created_at": "2026-01-05T00:00:00Z"}
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [empty, missing], [], []]

    assert await _port(http_client).fetch_review_context(repo="owner/repo", index=7) is None


async def test_fetch_review_context_is_none_when_nobody_wrote_anything():
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, [], [], []]

    assert await _port(http_client).fetch_review_context(repo="owner/repo", index=7) is None


async def test_fetch_review_context_says_whose_comment_it_is_even_without_a_login():
    """A host that refuses `/user` must not mark somebody else's comment as ours."""
    http_client = AsyncMock()
    http_client.get.side_effect = [{}, [INLINE_COMMENT], [], []]

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert context.findings == ()
    assert len(context.discussion) == 1
