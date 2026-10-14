from dataclasses import asdict
from unittest.mock import ANY, AsyncMock

import pytest

from revu.application.entities.review_marker import mark
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


REVU_BODY = mark("импорты лучше построчно")
INLINE_COMMENT = {
    "user": {"login": "revu-bot"},
    "body": REVU_BODY,
    "path": "app.py",
    "line": 12,
    "created_at": "2026-01-02T00:00:00Z",
}
REVIEW_BODY = {"user": {"login": "revu-bot"}, "body": mark("итог ревью"), "submitted_at": "2026-01-03T00:00:00Z"}
HUMAN_COMMENT = {"user": {"login": "ivan"}, "body": "как дела?", "created_at": "2026-01-01T00:00:00Z"}


def _context_client(
    issues: list[dict] | None = None,
    inline: list[dict] | None = None,
    reviews: list[dict] | None = None,
) -> AsyncMock:
    http_client = AsyncMock()
    http_client.get.side_effect = [issues or [], inline or [], reviews or []]

    return http_client


async def test_fetch_review_context_reads_every_conversation():
    """A pull request keeps its timeline, its inline comments and its reviews apart."""
    http_client = _context_client([HUMAN_COMMENT], [INLINE_COMMENT], [REVIEW_BODY])

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    urls = [call.kwargs["url"] for call in http_client.get.await_args_list]
    assert "repos/owner/repo/issues/7/comments" in urls[0]
    assert "repos/owner/repo/pulls/7/comments" in urls[1]
    assert "repos/owner/repo/pulls/7/reviews" in urls[2]


async def test_fetch_review_context_keeps_the_order_and_the_authors():
    context = await _port(_context_client([HUMAN_COMMENT], [INLINE_COMMENT], [REVIEW_BODY])).fetch_review_context(
        repo="owner/repo", index=7
    )

    assert context is not None
    assert [comment.author for comment in context.comments] == ["ivan", "revu-bot", "revu-bot"]
    assert [comment.body for comment in context.comments] == ["как дела?", "импорты лучше построчно", "итог ревью"]


async def test_fetch_review_context_finds_its_own_comments_by_signature():
    context = await _port(_context_client([HUMAN_COMMENT], [INLINE_COMMENT], [REVIEW_BODY])).fetch_review_context(
        repo="owner/repo", index=7
    )

    assert context is not None
    assert [comment.body for comment in context.findings] == ["импорты лучше построчно", "итог ревью"]
    assert [comment.body for comment in context.discussion] == ["как дела?"]


async def test_a_comment_by_the_same_account_without_the_signature_is_not_ours():
    """ReVu runs on the author's token; their own note is not an earlier review."""
    theirs = {"user": {"login": "revu-bot"}, "body": "WIP, не смотрите пока", "created_at": "2026-01-04T00:00:00Z"}
    http_client = _context_client([theirs])

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert context.findings == ()
    assert context.has_findings is False


async def test_fetch_review_context_keeps_the_place_of_an_inline_comment():
    context = await _port(_context_client(inline=[INLINE_COMMENT])).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    finding = context.findings[0]
    assert (finding.path, finding.line) == ("app.py", 12)
    # GitHub has no resolution state over REST.
    assert finding.resolved is False


async def test_fetch_review_context_falls_back_to_the_original_line():
    """GitHub nulls `line` once the anchor moves out of the diff."""
    moved = {**INLINE_COMMENT, "line": None, "original_line": 44}
    http_client = _context_client(inline=[moved])

    context = await _port(http_client).fetch_review_context(repo="owner/repo", index=7)

    assert context is not None
    assert context.findings[0].line == 44


async def test_fetch_review_context_skips_empty_bodies():
    """An approval or a label change carries no text worth showing."""
    empty = {"user": {"login": "revu-bot"}, "body": "   ", "created_at": "2026-01-04T00:00:00Z"}
    missing = {"user": {"login": "revu-bot"}, "created_at": "2026-01-05T00:00:00Z"}

    assert await _port(_context_client([empty, missing])).fetch_review_context(repo="owner/repo", index=7) is None


async def test_fetch_review_context_is_none_when_nobody_wrote_anything():
    assert await _port(_context_client()).fetch_review_context(repo="owner/repo", index=7) is None
