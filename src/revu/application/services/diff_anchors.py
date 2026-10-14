"""Inline comment anchors, checked against the diff they claim to point at.

A git host validates every anchor of a review request in one go, so a single
comment whose line is not in the diff (a hallucinated number, a stale file path)
makes the host reject the whole request: every other comment and the summary are
lost with it. Filtering the offenders out keeps the rest of the review.
"""

from collections.abc import Mapping
from dataclasses import dataclass, replace

from unidiff import PatchSet

from revu.application.config import get_logger
from revu.domain.entities.dto.ai_provider_dto import (
    BitbucketReviewCommentDTO,
    GiteaReviewCommentDTO,
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum

logger = get_logger(name=__name__)

GITHUB_SIDE_RIGHT = "RIGHT"
GITHUB_SIDE_LEFT = "LEFT"
BITBUCKET_ADDED = "ADDED"
BITBUCKET_REMOVED = "REMOVED"

_EMPTY_LINES: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class DiffAnchors:
    """Which file lines a diff actually contains.

    Added and removed lines are kept apart because Bitbucket anchors carry a
    ``lineType`` that has to match the kind of line; the two derived helpers
    expose the per-side view GitHub and Gitea need.
    """

    paths: frozenset[str]
    added: Mapping[str, frozenset[int]]
    removed: Mapping[str, frozenset[int]]
    context: Mapping[str, frozenset[tuple[int, int]]]

    @classmethod
    def from_diff(cls, diff_text: str) -> "DiffAnchors":
        added: dict[str, set[int]] = {}
        removed: dict[str, set[int]] = {}
        context: dict[str, set[tuple[int, int]]] = {}

        for patched_file in PatchSet(diff_text):
            path = patched_file.path
            added.setdefault(path, set())
            removed.setdefault(path, set())
            context.setdefault(path, set())

            for hunk in patched_file:
                for line in hunk:
                    # unidiff types both line numbers as optional; only one of
                    # them is set for an added or removed line.
                    if line.is_added and line.target_line_no is not None:
                        added[path].add(line.target_line_no)
                    elif line.is_removed and line.source_line_no is not None:
                        removed[path].add(line.source_line_no)
                    elif line.is_context and line.source_line_no is not None and line.target_line_no is not None:
                        context[path].add((line.source_line_no, line.target_line_no))

        return cls(
            paths=frozenset(added),
            added={path: frozenset(lines) for path, lines in added.items()},
            removed={path: frozenset(lines) for path, lines in removed.items()},
            context={path: frozenset(pairs) for path, pairs in context.items()},
        )

    def resolve_path(self, path: str) -> str | None:
        """Map a comment path onto a path this diff contains.

        The prompt asks for a bare repository path, but a leading ``a/`` or
        ``b/`` is a common slip, so it is accepted when the remainder matches.
        """
        candidate = (path or "").strip()

        if candidate in self.paths:
            return candidate

        for prefix in ("a/", "b/"):
            if candidate.startswith(prefix) and candidate[2:] in self.paths:
                return candidate[2:]

        return None

    def target_lines(self, path: str) -> frozenset[int]:
        """Lines of the new file: added lines plus context lines."""
        return self.added.get(path, _EMPTY_LINES) | frozenset(new for _, new in self.context.get(path, frozenset()))

    def source_lines(self, path: str) -> frozenset[int]:
        """Lines of the old file: removed lines plus context lines."""
        return self.removed.get(path, _EMPTY_LINES) | frozenset(old for old, _ in self.context.get(path, frozenset()))

    def is_github_anchor(self, path: str, side: str, line: int) -> bool:
        if side == GITHUB_SIDE_RIGHT:
            return line in self.target_lines(path)

        if side == GITHUB_SIDE_LEFT:
            return line in self.source_lines(path)

        return False

    def is_gitea_anchor(self, path: str, old_position: int, new_position: int) -> bool:
        # A context comment is expressed as the pair of both line numbers; a
        # comment on one side carries 0 for the other. The one-sided forms are
        # matched against the whole side rather than only added/removed lines:
        # Gitea's position semantics have changed across versions, and sending a
        # comment the host accepts is better than dropping a valid one.
        return (
            (old_position, new_position) in self.context.get(path, frozenset())
            or (old_position == 0 and new_position in self.target_lines(path))
            or (new_position == 0 and old_position in self.source_lines(path))
        )

    def is_gitlab_anchor(self, path: str, old_line: int | None, new_line: int | None) -> bool:
        # GitLab addresses a note by the line on each side of the diff: an added
        # line has only a new line, a removed line only an old one, and a context
        # line needs both. Sending the wrong combination is rejected outright.
        if new_line is None and old_line is None:
            return False

        if old_line is None:
            return new_line in self.added.get(path, _EMPTY_LINES)

        if new_line is None:
            return old_line in self.removed.get(path, _EMPTY_LINES)

        return (old_line, new_line) in self.context.get(path, frozenset())

    def is_bitbucket_anchor(self, path: str, line_type: str, line: int) -> bool:
        # Bitbucket rejects a `lineType` that contradicts the diff, so the kind
        # of line is checked exactly here.
        if line_type == BITBUCKET_ADDED:
            return line in self.added.get(path, _EMPTY_LINES)

        if line_type == BITBUCKET_REMOVED:
            return line in self.removed.get(path, _EMPTY_LINES)

        # A context line exists on both sides and Bitbucket accepts either
        # numbering.
        return line in self.target_lines(path) or line in self.source_lines(path)


def _is_anchored(comment: object, anchors: DiffAnchors, git_host: GitProviderEnum) -> bool:
    """Whether one comment points at a line the diff really contains."""
    match git_host:
        case GitProviderEnum.GITHUB:
            if not isinstance(comment, GitHubReviewCommentDTO):
                return False

            path = anchors.resolve_path(comment.path)

            return path is not None and anchors.is_github_anchor(path, comment.side, comment.line)

        case GitProviderEnum.GITEA:
            if not isinstance(comment, GiteaReviewCommentDTO):
                return False

            path = anchors.resolve_path(comment.path)

            return path is not None and anchors.is_gitea_anchor(path, comment.old_position, comment.new_position)

        case GitProviderEnum.GITLAB:
            if not isinstance(comment, GitLabReviewCommentDTO):
                return False

            path = anchors.resolve_path(comment.path)

            return path is not None and anchors.is_gitlab_anchor(path, comment.old_line, comment.new_line)

        case GitProviderEnum.BITBUCKET:
            if not isinstance(comment, BitbucketReviewCommentDTO):
                return False

            path = anchors.resolve_path(comment.path)

            return path is not None and anchors.is_bitbucket_anchor(path, comment.lineType, comment.line)

        case _:
            # Unreachable: the configuration validator rejects other hosts.
            return False


def drop_unanchored_comments(
    review: ReviewResponseDTO,
    anchors: DiffAnchors,
    git_host: GitProviderEnum,
) -> tuple[ReviewResponseDTO, int]:
    """Return the review without comments that point outside the diff.

    The second element is how many comments were dropped, so the caller can say
    so in the log instead of silently reviewing less.
    """
    kept = [comment for comment in review.comments if _is_anchored(comment, anchors, git_host)]

    return replace(review, comments=kept), len(review.comments) - len(kept)
