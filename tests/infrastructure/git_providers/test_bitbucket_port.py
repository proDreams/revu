from unittest.mock import ANY, AsyncMock

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    BitBucketReviewCommentDTO,
    GithubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)
from revu.infrastructure.git_providers.bitbucket.bitbucket_port import BitbucketPort

pytestmark = pytest.mark.unit

COMMIT_SHA = "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"

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


def test_get_headers(settings):
    port = BitbucketPort(http_client=AsyncMock())

    assert port._get_headers() == {"Authorization": f"Bearer {settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN}"}


async def test_fetch_diff_converts_json_diff_to_unified(settings):
    http_client = AsyncMock()
    http_client.get.return_value = {**DIFF_PAGE, "isLastPage": True}

    port = BitbucketPort(http_client=http_client)

    result = await port.fetch_diff(repo="PROJ/my-repo", index=42)

    http_client.get.assert_awaited_once_with(url=ANY, headers=port._get_headers())
    assert "projects/PROJ/my-repo/pull-requests/42/diff" in http_client.get.await_args.kwargs["url"]
    assert "diff --git a/app.py b/app.py" in result
    assert "@@ -1,2 +1,2 @@" in result
    assert "+new" in result


async def test_fetch_diff_follows_pagination(settings):
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

    port = BitbucketPort(http_client=http_client)

    result = await port.fetch_diff(repo="PROJ/my-repo", index=42)

    assert http_client.get.await_count == 2
    assert "app.py" in result
    assert "other.py" in result
    assert "second page" in result
    assert "start=1" in http_client.get.await_args_list[1].kwargs["url"]


async def test_fetch_diff_stops_when_the_server_repeats_a_page(settings):
    """A misbehaving server must not make the pagination loop forever."""
    http_client = AsyncMock()
    http_client.get.return_value = {**DIFF_PAGE, "isLastPage": False, "nextPageStart": 0}

    port = BitbucketPort(http_client=http_client)

    result = await port.fetch_diff(repo="PROJ/my-repo", index=42)

    assert http_client.get.await_count == 1
    assert "app.py" in result


async def test_fetch_diff_tolerates_a_non_object_page(settings):
    http_client = AsyncMock()
    http_client.get.return_value = None

    port = BitbucketPort(http_client=http_client)

    assert await port.fetch_diff(repo="PROJ/my-repo", index=42) == ""


async def test_send_comment(settings):
    http_client = AsyncMock(post=AsyncMock())
    port = BitbucketPort(http_client=http_client)

    await port.send_comment(repo_owner="PROJ/my-repo", review="looks good", index=42)

    http_client.post.assert_awaited_once_with(url=ANY, headers=ANY, payload={"text": "looks good"})
    assert "projects/PROJ/my-repo/pull-requests/42/comments" in http_client.post.await_args.kwargs["url"]


async def test_send_inline_anchors_on_comment_line(settings):
    """The anchor line must be the commented line, not the pull request number."""
    http_client = AsyncMock(post=AsyncMock())
    port = BitbucketPort(http_client=http_client)

    review = ReviewResponseDTO(
        general_comment="overall feedback",
        comments=[
            BitBucketReviewCommentDTO(path="app.py", lineType="ADDED", body="fix this", line=17),
        ],
    )

    await port.send_inline(sha=COMMIT_SHA, repo_owner="PROJ/my-repo", review=review, index=42)

    assert http_client.post.await_count == 2

    inline_payload = http_client.post.await_args_list[0].kwargs["payload"]
    assert inline_payload == {
        "text": "fix this",
        "anchor": {"path": "app.py", "lineType": "ADDED", "line": 17, "diffType": "EFFECTIVE"},
    }

    general_payload = http_client.post.await_args_list[1].kwargs["payload"]
    assert general_payload == {"text": "overall feedback"}


async def test_send_inline_rejects_foreign_comment_types(settings):
    http_client = AsyncMock(post=AsyncMock())
    port = BitbucketPort(http_client=http_client)

    review = ReviewResponseDTO(
        general_comment="overall feedback",
        comments=[GithubReviewCommentDTO(path="app.py", line=1, body="fix this")],
    )

    with pytest.raises(UnsupportedReviewCommentException, match="cannot be published to Bitbucket"):
        await port.send_inline(sha=COMMIT_SHA, repo_owner="PROJ/my-repo", review=review, index=42)

    http_client.post.assert_not_awaited()
