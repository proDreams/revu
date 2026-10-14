"""What a pull request already says, read before a review starts.

A second review that ignores its own earlier findings repeats them and loses the
thread of the discussion. The ports gather the comments the pull request already
carries — ReVu's own findings and everyone else's discussion — and the prompt uses
them to check what was fixed.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PreviousCommentDTO:
    """One comment already published on the pull request."""

    author: str
    body: str
    #: True when ReVu itself wrote it, which is what makes it a finding to verify.
    is_revu: bool = False
    path: str | None = None
    line: int | None = None
    #: The host reports a resolution state (GitLab, Bitbucket) or it does not (GitHub).
    resolved: bool = False


@dataclass(frozen=True, slots=True)
class ReviewContextDTO:
    """The comments a pull request already has, oldest first."""

    comments: tuple[PreviousCommentDTO, ...] = ()

    @property
    def findings(self) -> tuple[PreviousCommentDTO, ...]:
        """ReVu's own earlier comments: the ones a re-review has to check."""
        return tuple(comment for comment in self.comments if comment.is_revu)

    @property
    def discussion(self) -> tuple[PreviousCommentDTO, ...]:
        """Everything the other participants said, as context."""
        return tuple(comment for comment in self.comments if not comment.is_revu)

    @property
    def has_findings(self) -> bool:
        """Whether ReVu has reviewed this pull request before."""
        return any(comment.is_revu for comment in self.comments)
