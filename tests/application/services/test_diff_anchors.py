"""Inline comments are checked against the diff before they are published."""

import pytest

from revu.application.services.diff_anchors import (
    DiffAnchors,
    drop_unanchored_comments,
)
from revu.domain.entities.dto.ai_provider_dto import (
    BitbucketReviewCommentDTO,
    GiteaReviewCommentDTO,
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum

pytestmark = pytest.mark.unit

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -10,3 +10,4 @@ def handler():
 context ten
-removed eleven
+added eleven
+added twelve
 context thirteen
"""

ADDED_FILE_DIFF = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+first line
+second line
"""


@pytest.fixture
def anchors() -> DiffAnchors:
    return DiffAnchors.from_diff(DIFF)


def test_paths_are_indexed(anchors):
    assert anchors.paths == frozenset({"app.py"})


def test_added_and_removed_lines_are_kept_apart(anchors):
    # "context ten" = old 10/new 10, "removed eleven" = old 11,
    # "added eleven"/"added twelve" = new 11/12, "context thirteen" = old 12/new 13.
    assert anchors.added["app.py"] == frozenset({11, 12})
    assert anchors.removed["app.py"] == frozenset({11})
    assert anchors.context["app.py"] == frozenset({(10, 10), (12, 13)})


def test_the_per_side_views_include_context_lines(anchors):
    assert anchors.target_lines("app.py") == frozenset({10, 11, 12, 13})
    assert anchors.source_lines("app.py") == frozenset({10, 11, 12})
    assert anchors.target_lines("unknown.py") == frozenset()


def test_a_new_file_has_added_lines_only():
    new_file = DiffAnchors.from_diff(ADDED_FILE_DIFF)

    assert new_file.added["new.py"] == frozenset({1, 2})
    assert new_file.removed["new.py"] == frozenset()
    assert new_file.context["new.py"] == frozenset()


def test_an_empty_diff_has_no_anchors():
    assert DiffAnchors.from_diff("").paths == frozenset()


@pytest.mark.parametrize("path", ["app.py", "b/app.py", "a/app.py", "  app.py  "])
def test_a_known_path_resolves(anchors, path):
    assert anchors.resolve_path(path) == "app.py"


@pytest.mark.parametrize("path", ["other.py", "app.pyc", ""])
def test_an_unknown_path_does_not_resolve(anchors, path):
    assert anchors.resolve_path(path) is None


@pytest.mark.parametrize(
    ("side", "line", "expected"),
    [
        ("RIGHT", 11, True),
        ("RIGHT", 12, True),
        ("RIGHT", 10, True),
        ("LEFT", 11, True),
        ("LEFT", 13, False),  # added line 13 exists only in the new file
        ("RIGHT", 99, False),
        ("SIDEWAYS", 11, False),
    ],
)
def test_github_anchors(anchors, side, line, expected):
    assert anchors.is_github_anchor("app.py", side, line) is expected


@pytest.mark.parametrize(
    ("old_position", "new_position", "expected"),
    [
        (0, 12, True),  # added line
        (11, 0, True),  # removed line
        (10, 10, True),  # context pair
        (12, 13, True),  # context pair
        (0, 99, False),
        (99, 0, False),
        (0, 0, False),
        (10, 11, False),  # not a context pair
    ],
)
def test_gitea_anchors(anchors, old_position, new_position, expected):
    assert anchors.is_gitea_anchor("app.py", old_position, new_position) is expected


@pytest.mark.parametrize(
    ("old_line", "new_line", "expected"),
    [
        (None, 11, True),  # added line: new side only
        (None, 12, True),
        (11, None, True),  # removed line: old side only
        (10, 10, True),  # context: both sides
        (12, 13, True),
        (None, 13, False),  # 13 is a context line, not an added one
        (12, None, False),  # 12 was added, not removed
        (10, None, False),  # 10 is a context line, not a removed one
        (10, 11, False),  # not a context pair
        (None, None, False),  # no side at all cannot be positioned
    ],
)
def test_gitlab_anchors(anchors, old_line, new_line, expected):
    assert anchors.is_gitlab_anchor("app.py", old_line, new_line) is expected


@pytest.mark.parametrize(
    ("line_type", "line", "expected"),
    [
        ("ADDED", 11, True),
        ("ADDED", 10, False),  # 10 is a context line, not an added one
        ("REMOVED", 11, True),
        ("REMOVED", 12, False),  # 12 is a context line, not a removed one
        ("CONTEXT", 10, True),
        ("CONTEXT", 12, True),  # context accepts either side
        ("CONTEXT", 99, False),
    ],
)
def test_bitbucket_anchors(anchors, line_type, line, expected):
    assert anchors.is_bitbucket_anchor("app.py", line_type, line) is expected


def _review(*comments) -> ReviewResponseDTO:
    return ReviewResponseDTO(general_comment="summary", comments=list(comments))


def test_the_general_comment_is_always_kept(anchors):
    review, dropped = drop_unanchored_comments(
        _review(GitHubReviewCommentDTO(path="app.py", line=12, body="ok")),
        anchors,
        GitProviderEnum.GITHUB,
    )

    assert review.general_comment == "summary"
    assert dropped == 0
    assert len(review.comments) == 1


def test_github_comments_outside_the_diff_are_dropped(anchors):
    review, dropped = drop_unanchored_comments(
        _review(
            GitHubReviewCommentDTO(path="app.py", line=12, side="RIGHT", body="kept"),
            GitHubReviewCommentDTO(path="app.py", line=500, side="RIGHT", body="dropped"),
            GitHubReviewCommentDTO(path="app.py", line=13, side="LEFT", body="dropped too"),
            GitHubReviewCommentDTO(path="missing.py", line=12, side="RIGHT", body="dropped as well"),
        ),
        anchors,
        GitProviderEnum.GITHUB,
    )

    assert [comment.body for comment in review.comments] == ["kept"]
    assert dropped == 3


def test_gitea_comments_outside_the_diff_are_dropped(anchors):
    review, dropped = drop_unanchored_comments(
        _review(
            GiteaReviewCommentDTO(path="app.py", old_position=0, new_position=12, body="kept"),
            GiteaReviewCommentDTO(path="app.py", old_position=0, new_position=500, body="dropped"),
        ),
        anchors,
        GitProviderEnum.GITEA,
    )

    assert [comment.body for comment in review.comments] == ["kept"]
    assert dropped == 1


def test_bitbucket_comments_outside_the_diff_are_dropped(anchors):
    review, dropped = drop_unanchored_comments(
        _review(
            BitbucketReviewCommentDTO(path="app.py", line=11, lineType="REMOVED", body="kept"),
            BitbucketReviewCommentDTO(path="app.py", line=10, lineType="ADDED", body="dropped"),
        ),
        anchors,
        GitProviderEnum.BITBUCKET,
    )

    assert [comment.body for comment in review.comments] == ["kept"]
    assert dropped == 1


# A comment built for a different host must never reach the git host.
FOREIGN_COMMENTS = {
    GitProviderEnum.GITHUB: GiteaReviewCommentDTO(path="app.py", old_position=0, new_position=12, body="foreign"),
    GitProviderEnum.GITEA: GitHubReviewCommentDTO(path="app.py", line=12, body="foreign"),
    GitProviderEnum.BITBUCKET: GitHubReviewCommentDTO(path="app.py", line=12, body="foreign"),
    GitProviderEnum.GITLAB: GitHubReviewCommentDTO(path="app.py", line=12, body="foreign"),
}

MATCHING_COMMENTS = {
    GitProviderEnum.GITHUB: GitHubReviewCommentDTO(path="app.py", line=12, side="RIGHT", body="ok"),
    GitProviderEnum.GITEA: GiteaReviewCommentDTO(path="app.py", old_position=0, new_position=12, body="ok"),
    GitProviderEnum.BITBUCKET: BitbucketReviewCommentDTO(path="app.py", line=11, lineType="REMOVED", body="ok"),
    GitProviderEnum.GITLAB: GitLabReviewCommentDTO(path="app.py", new_line=12, body="ok"),
}


@pytest.mark.parametrize("git_host", list(GitProviderEnum))
def test_a_comment_of_another_host_is_dropped(anchors, git_host):
    """Belt and braces: a foreign DTO must never reach the git host."""
    review, dropped = drop_unanchored_comments(_review(FOREIGN_COMMENTS[git_host]), anchors, git_host)

    assert review.comments == []
    assert dropped == 1


@pytest.mark.parametrize("git_host", list(GitProviderEnum))
def test_a_matching_comment_is_kept(anchors, git_host):
    review, dropped = drop_unanchored_comments(_review(MATCHING_COMMENTS[git_host]), anchors, git_host)

    assert len(review.comments) == 1
    assert dropped == 0


def test_an_unknown_host_drops_everything(anchors):
    review, dropped = drop_unanchored_comments(
        _review(GitHubReviewCommentDTO(path="app.py", line=12, body="x")),
        anchors,
        "sourceforge",  # type: ignore[arg-type]
    )

    assert review.comments == []
    assert dropped == 1
