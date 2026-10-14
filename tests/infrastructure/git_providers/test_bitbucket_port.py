from unittest.mock import ANY, AsyncMock

import pytest

from revu.application.entities.review_marker import mark
from revu.domain.entities.dto.ai_provider_dto import (
    BitbucketReviewCommentDTO,
    GitHubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)
from revu.infrastructure.git_providers.bitbucket.bitbucket_port import BitbucketPort
from tests.conftest import make_connection

pytestmark = pytest.mark.unit

COMMIT_SHA = "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"
BITBUCKET_URL = "https://bitbucket.internal"

DIFF_PAGE = {
    "diffs": [
        {
            "source": {"toString": "app.py"},
            "destination": {"toString": "app.py"},
            "hunks": [
                {
                    "sourceLine": 1,
                    "sourceSpan": 2,
                    "destinationLine": 1,
                    "destinationSpan": 2,
                    "segments": [
                        {"type": "CONTEXT", "lines": [{"line": "context"}]},
                        {"type": "REMOVED", "lines": [{"line": "old"}]},
                        {"type": "ADDED", "lines": [{"line": "new"}]},
                    ],
                }
            ],
        }
    ]
}


def _port(http_client: AsyncMock, **connection) -> BitbucketPort:
    config = make_connection(
        key="bb-client",
        host=GitProviderEnum.BITBUCKET,
        user_token="bitbucket-token",
        base_url=BITBUCKET_URL,
        **connection,
    )

    return BitbucketPort(http_client=http_client, config=config)


def test_get_headers():
    assert _port(AsyncMock())._get_headers() == {"Authorization": "Bearer bitbucket-token"}


async def test_fetch_diff_converts_json_diff_to_unified():
    http_client = AsyncMock()
    http_client.get.return_value = {**DIFF_PAGE, "isLastPage": True}

    result = await _port(http_client).fetch_diff(repo="PROJ/my-repo", index=42)

    http_client.get.assert_awaited_once_with(url=ANY, headers=_port(AsyncMock())._get_headers())
    assert "projects/PROJ/my-repo/pull-requests/42/diff" in http_client.get.await_args.kwargs["url"]
    assert "diff --git a/app.py b/app.py" in result
    assert "@@ -1,2 +1,2 @@" in result
    assert "+new" in result


async def test_fetch_diff_follows_pagination():
    """Only the first page used to be converted, truncating large reviews."""
    second_page = {
        "diffs": [
            {
                "source": {"toString": "other.py"},
                "destination": {"toString": "other.py"},
                "hunks": [
                    {
                        "sourceLine": 5,
                        "sourceSpan": 1,
                        "destinationLine": 5,
                        "destinationSpan": 1,
                        "segments": [{"type": "ADDED", "lines": [{"line": "second page"}]}],
                    }
                ],
            }
        ],
        "isLastPage": True,
    }
    http_client = AsyncMock()
    http_client.get.side_effect = [{**DIFF_PAGE, "isLastPage": False, "nextPageStart": 1}, second_page]

    result = await _port(http_client).fetch_diff(repo="PROJ/my-repo", index=42)

    assert http_client.get.await_count == 2
    assert "app.py" in result
    assert "other.py" in result
    assert "second page" in result
    assert "start=1" in http_client.get.await_args_list[1].kwargs["url"]


async def test_fetch_diff_stops_when_the_server_repeats_a_page():
    """A misbehaving server must not make the pagination loop forever."""
    http_client = AsyncMock()
    http_client.get.return_value = {**DIFF_PAGE, "isLastPage": False, "nextPageStart": 0}

    result = await _port(http_client).fetch_diff(repo="PROJ/my-repo", index=42)

    assert http_client.get.await_count == 1
    assert "app.py" in result


async def test_fetch_diff_tolerates_a_non_object_page():
    http_client = AsyncMock()
    http_client.get.return_value = None

    assert await _port(http_client).fetch_diff(repo="PROJ/my-repo", index=42) == ""


async def test_send_comment():
    http_client = AsyncMock(post=AsyncMock())

    await _port(http_client).send_comment(repo_owner="PROJ/my-repo", review="looks good", index=42)

    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"text": "looks good"})
    assert "projects/PROJ/my-repo/pull-requests/42/comments" in http_client.post.await_args.kwargs["url"]


async def test_send_inline_anchors_on_comment_line():
    """The anchor line must be the commented line, not the pull request number."""
    http_client = AsyncMock(post=AsyncMock())
    review = ReviewResponseDTO(
        general_comment="overall feedback",
        comments=[BitbucketReviewCommentDTO(path="app.py", lineType="ADDED", body="fix this", line=17)],
    )

    await _port(http_client).send_inline(sha=COMMIT_SHA, repo_owner="PROJ/my-repo", review=review, index=42)

    assert http_client.post.await_count == 2

    inline_payload = http_client.post.await_args_list[0].kwargs["payload"]
    assert inline_payload == {
        "text": "fix this",
        "anchor": {"path": "app.py", "lineType": "ADDED", "line": 17, "diffType": "EFFECTIVE"},
    }
    assert http_client.post.await_args_list[1].kwargs["payload"] == {"text": "overall feedback"}


async def test_send_inline_rejects_foreign_comment_types():
    http_client = AsyncMock(post=AsyncMock())
    review = ReviewResponseDTO(
        general_comment="overall feedback",
        comments=[GitHubReviewCommentDTO(path="app.py", line=1, body="fix this")],
    )

    with pytest.raises(UnsupportedReviewCommentException, match="cannot be published to Bitbucket"):
        await _port(http_client).send_inline(sha=COMMIT_SHA, repo_owner="PROJ/my-repo", review=review, index=42)

    http_client.post.assert_not_awaited()


OURS = {
    "author": {"name": "ivan", "slug": "ivan"},
    "text": mark("импорты лучше построчно"),
    "state": "OPEN",
    "createdDate": 1767225600000,
    "anchor": {"path": {"toString": "app.py"}, "line": 12, "lineType": "ADDED"},
}
REPLY = {"author": {"name": "ivan"}, "text": "поправил", "state": "RESOLVED", "createdDate": 1767312000000}


def _comments_client(values: list[dict], *, is_last: bool = True, **page_extra) -> AsyncMock:
    http_client = AsyncMock()
    http_client.get.return_value = {"values": values, "isLastPage": is_last, **page_extra}

    return http_client


async def test_fetch_review_context_reads_comments_with_their_anchor():
    http_client = _comments_client([OURS])

    context = await _port(http_client).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    comment = context.comments[0]
    assert (comment.author, comment.body) == ("ivan", "импорты лучше построчно")
    assert (comment.path, comment.line) == ("app.py", 12)
    assert comment.is_revu is True
    assert "comments?limit=" in http_client.get.await_args.kwargs["url"]


async def test_a_same_account_comment_without_the_signature_is_not_ours():
    """The token's owner is the author, so authorship proves nothing here."""
    theirs = {**OURS, "text": "WIP, не смотрите"}

    context = await _port(_comments_client([theirs])).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    assert context.findings == ()
    assert context.discussion[0].body == "WIP, не смотрите"


async def test_fetch_review_context_flattens_replies():
    """Bitbucket nests a thread's replies under the comment that started it."""
    thread = {**OURS, "comments": [REPLY]}

    context = await _port(_comments_client([thread])).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    assert [comment.body for comment in context.comments] == ["импорты лучше построчно", "поправил"]
    assert context.discussion[0].resolved is True


async def test_fetch_review_context_follows_pages():
    second = {**OURS, "text": mark("второй"), "createdDate": 1767398400000}
    http_client = AsyncMock()
    http_client.get.side_effect = [
        {"values": [OURS], "isLastPage": False, "nextPageStart": 1},
        {"values": [second], "isLastPage": True},
    ]

    context = await _port(http_client).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    assert [comment.body for comment in context.comments] == ["импорты лучше построчно", "второй"]
    assert http_client.get.await_count == 2
    assert "start=1" in http_client.get.await_args.kwargs["url"]


async def test_fetch_review_context_stops_on_an_unexpected_payload():
    http_client = AsyncMock()
    http_client.get.return_value = ["nonsense"]

    assert await _port(http_client).fetch_review_context(repo="MYPROJ/repo", index=7) is None


async def test_fetch_review_context_skips_textless_comments():
    assert (
        await _port(_comments_client([{**OURS, "text": "  "}])).fetch_review_context(repo="MYPROJ/repo", index=7)
        is None
    )


@pytest.mark.parametrize("author", [None, {}, {"displayName": 42}, "not-a-dict"])
async def test_fetch_review_context_survives_a_comment_without_a_usable_author(author):
    http_client = _comments_client([{"text": "кто-то написал", "author": author, "createdDate": 1767225600000}, "x"])

    context = await _port(http_client).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    assert [comment.author for comment in context.comments] == [""]
    assert context.findings == ()


async def test_fetch_review_context_stops_at_the_reply_depth_limit():
    """A malformed payload must not make the flattening recursive forever."""
    nested: dict = {"text": "reply", "author": {"name": "ivan"}, "createdDate": 1767225600000}
    for _ in range(8):
        nested = {"text": "parent", "author": {"name": "ivan"}, "createdDate": 1767225600000, "comments": [nested]}

    context = await _port(_comments_client([nested])).fetch_review_context(repo="MYPROJ/repo", index=7)

    assert context is not None
    assert len(context.comments) == 6  # the root plus five levels of replies
