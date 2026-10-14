from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.provider_exceptions import (
    GitProviderException,
)
from revu.domain.entities.dto.ai_provider_dto import (
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)
from revu.infrastructure.git_providers.gitlab.gitlab_port import (
    DIFF_PAGE_SIZE,
    GitlabPort,
)
from tests.conftest import make_connection

pytestmark = pytest.mark.unit

GITLAB_URL = "https://gitlab.internal"

VERSIONS = [
    {
        "id": 1,
        "head_commit_sha": "c" * 40,
        "base_commit_sha": "a" * 40,
        "start_commit_sha": "b" * 40,
    }
]


def _port(http_client: AsyncMock, base_url: str | None = GITLAB_URL) -> GitlabPort:
    config = make_connection(
        key="gl-main",
        host=GitProviderEnum.GITLAB,
        user_token="gitlab-token",
        base_url=base_url,
    )

    return GitlabPort(http_client=http_client, config=config)


def test_get_headers():
    assert _port(AsyncMock())._get_headers() == {"PRIVATE-TOKEN": "gitlab-token"}


def test_the_public_instance_is_the_default():
    """gitlab.com needs no base URL; self-managed instances do."""
    port = _port(AsyncMock(), base_url=None)

    assert port.gitlab_url == GitlabPort.DEFAULT_API_URL == "https://gitlab.com"


def test_a_project_path_is_url_encoded():
    """GitLab takes an id or a full `group/project` path, the latter encoded."""
    assert GitlabPort._project("group/sub/project") == "group%2Fsub%2Fproject"


async def test_fetch_diff_requests_the_encoded_project():
    http_client = AsyncMock()
    http_client.get.return_value = []

    await _port(http_client).fetch_diff(repo="group/project", index=11)

    assert http_client.get.await_args.kwargs["url"] == (
        f"{GITLAB_URL}/api/v4/projects/group%2Fproject/merge_requests/11/diffs?per_page={DIFF_PAGE_SIZE}&page=1"
    )
    assert http_client.get.await_args.kwargs["headers"] == {"PRIVATE-TOKEN": "gitlab-token"}


async def test_fetch_diff_follows_pages_until_a_short_one():
    full_page = [{"old_path": f"f{i}.py", "new_path": f"f{i}.py", "diff": "@@ -1 +1 @@"} for i in range(DIFF_PAGE_SIZE)]
    last_page = [{"old_path": "last.py", "new_path": "last.py", "diff": "@@ -1 +1 @@"}]

    http_client = AsyncMock()
    http_client.get.side_effect = [full_page, last_page]

    unified = await _port(http_client).fetch_diff(repo="group/project", index=11)

    assert http_client.get.await_count == 2
    assert "last.py" in unified
    assert unified.count("diff --git") == DIFF_PAGE_SIZE + 1


async def test_fetch_diff_stops_when_a_page_is_empty():
    """A full page promises more; an empty one ends the run."""
    full_page = [{"old_path": f"f{i}.py", "new_path": f"f{i}.py", "diff": "@@"} for i in range(DIFF_PAGE_SIZE)]

    http_client = AsyncMock()
    http_client.get.side_effect = [full_page, []]

    unified = await _port(http_client).fetch_diff(repo="group/project", index=11)

    assert http_client.get.await_count == 2
    assert unified.count("diff --git") == DIFF_PAGE_SIZE


async def test_fetch_diff_stops_on_a_payload_that_is_not_a_list():
    http_client = AsyncMock()
    http_client.get.return_value = {"message": "404 Project Not Found"}

    assert await _port(http_client).fetch_diff(repo="group/project", index=11) == ""
    assert http_client.get.await_count == 1


async def test_send_comment_posts_a_note():
    http_client = AsyncMock()

    await _port(http_client).send_comment(repo_owner="group/project", review="summary", index=11)

    assert http_client.post.await_args.kwargs["url"] == (
        f"{GITLAB_URL}/api/v4/projects/group%2Fproject/merge_requests/11/notes"
    )
    assert http_client.post.await_args.kwargs["payload"] == {"body": "summary"}


async def test_send_inline_positions_a_note_with_the_three_shas():
    http_client = AsyncMock()
    http_client.get.return_value = VERSIONS

    review = ReviewResponseDTO(
        general_comment="summary",
        comments=[GitLabReviewCommentDTO(path="app.py", new_line=12, body="added line")],
    )

    await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    http_client.get.assert_awaited_once_with(
        url=f"{GITLAB_URL}/api/v4/projects/group%2Fproject/merge_requests/11/versions",
        headers={"PRIVATE-TOKEN": "gitlab-token"},
    )

    discussion = http_client.post.await_args_list[0].kwargs
    assert discussion["url"] == f"{GITLAB_URL}/api/v4/projects/group%2Fproject/merge_requests/11/discussions"
    assert discussion["payload"] == {
        "body": "added line",
        "position": {
            "position_type": "text",
            "base_sha": "a" * 40,
            "head_sha": "c" * 40,
            "start_sha": "b" * 40,
            "new_path": "app.py",
            "old_path": "app.py",
            "new_line": 12,
        },
    }

    # The summary follows the inline notes.
    assert http_client.post.await_args_list[-1].kwargs["payload"] == {"body": "summary"}


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        (GitLabReviewCommentDTO(path="a.py", old_line=5, body="b"), {"old_line": 5}),
        (GitLabReviewCommentDTO(path="a.py", new_line=7, old_line=5, body="b"), {"new_line": 7, "old_line": 5}),
    ],
)
async def test_a_note_carries_only_the_lines_it_has(comment, expected):
    http_client = AsyncMock()
    http_client.get.return_value = VERSIONS

    review = ReviewResponseDTO(general_comment="summary", comments=[comment])

    await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    position = http_client.post.await_args_list[0].kwargs["payload"]["position"]

    for key, value in expected.items():
        assert position[key] == value

    assert len([key for key in ("new_line", "old_line") if key in position]) == len(expected)


async def test_the_versions_are_fetched_once_per_review():
    """Two comments must not cost two extra requests."""
    http_client = AsyncMock()
    http_client.get.return_value = VERSIONS

    review = ReviewResponseDTO(
        general_comment="summary",
        comments=[
            GitLabReviewCommentDTO(path="a.py", new_line=1, body="first"),
            GitLabReviewCommentDTO(path="b.py", new_line=2, body="second"),
        ],
    )

    await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    assert http_client.get.await_count == 1
    # Two discussions and the summary.
    assert http_client.post.await_count == 3


async def test_inline_without_comments_does_not_ask_for_versions():
    http_client = AsyncMock()

    review = ReviewResponseDTO(general_comment="summary", comments=[])

    await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    http_client.get.assert_not_awaited()
    assert http_client.post.await_count == 1


@pytest.mark.parametrize(
    "versions",
    [
        [],
        [{"head_commit_sha": "c" * 40}],
        [{"base_commit_sha": None, "head_commit_sha": "c" * 40, "start_commit_sha": "b" * 40}],
        "not-a-list",
    ],
)
async def test_incomplete_diff_versions_are_reported(versions):
    """Without the three SHAs GitLab cannot place a note at all."""
    http_client = AsyncMock()
    http_client.get.return_value = versions

    review = ReviewResponseDTO(
        general_comment="summary",
        comments=[GitLabReviewCommentDTO(path="a.py", new_line=1, body="b")],
    )

    with pytest.raises(GitProviderException) as exc_info:
        await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    assert "merge request 11" in str(exc_info.value)


async def test_a_comment_of_another_host_is_rejected():
    http_client = AsyncMock()

    review = ReviewResponseDTO(
        general_comment="summary",
        comments=[GitHubReviewCommentDTO(path="a.py", line=1, body="foreign")],
    )

    with pytest.raises(UnsupportedReviewCommentException):
        await _port(http_client).send_inline(sha="x", repo_owner="group/project", review=review, index=11)

    http_client.post.assert_not_awaited()


BOT = {"username": "revu-bot"}
SYSTEM_NOTE = {"body": "changed the description", "system": True, "author": BOT, "created_at": "2026-01-01T00:00:00Z"}
OUR_NOTE = {
    "body": "импорты лучше построчно",
    "author": BOT,
    "resolved": True,
    "created_at": "2026-01-02T00:00:00Z",
    "position": {"new_path": "app.py", "new_line": 12},
}
THEIR_NOTE = {
    "body": "не трогаем этот модуль",
    "author": {"username": "ivan"},
    "created_at": "2026-01-03T00:00:00Z",
    "position": {"old_path": "legacy.py", "old_line": 4},
}


def _context_client() -> AsyncMock:
    http_client = AsyncMock()
    empty = {"body": "   ", "author": BOT, "created_at": "2026-01-04T00:00:00Z"}
    http_client.get.side_effect = [BOT, [SYSTEM_NOTE, empty, OUR_NOTE, THEIR_NOTE]]

    return http_client


async def test_fetch_review_context_reads_notes_and_skips_system_ones():
    http_client = _context_client()

    context = await _port(http_client).fetch_review_context(repo="group/project", index=11)

    assert context is not None
    assert [comment.body for comment in context.comments] == [
        "импорты лучше построчно",
        "не трогаем этот модуль",
    ]
    assert [call.kwargs["url"] for call in http_client.get.await_args_list][0] == (f"{GITLAB_URL}/api/v4/user")
    assert "sort=asc" in http_client.get.await_args_list[1].kwargs["url"]


async def test_fetch_review_context_marks_revu_notes_and_their_resolution():
    context = await _port(_context_client()).fetch_review_context(repo="group/project", index=11)

    assert context is not None
    assert context.findings[0].is_revu is True
    assert context.findings[0].resolved is True
    assert context.discussion[0].is_revu is False


async def test_fetch_review_context_keeps_the_diff_position():
    context = await _port(_context_client()).fetch_review_context(repo="group/project", index=11)

    assert context is not None
    assert (context.findings[0].path, context.findings[0].line) == ("app.py", 12)
    # A note on a removed line only carries the old one.
    assert (context.discussion[0].path, context.discussion[0].line) == ("legacy.py", 4)


async def test_fetch_review_context_is_none_without_notes():
    http_client = AsyncMock()
    http_client.get.side_effect = [BOT, []]

    assert await _port(http_client).fetch_review_context(repo="group/project", index=11) is None
