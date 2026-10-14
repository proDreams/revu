from dataclasses import dataclass

from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)


@dataclass
class GitHubReviewCommentDTO:
    """A GitHub inline comment: ``line`` is a file line number, ``side`` its version."""

    path: str
    line: int
    body: str
    side: str = "RIGHT"


@dataclass
class GiteaReviewCommentDTO:
    path: str
    old_position: int
    new_position: int
    body: str


@dataclass
class BitbucketReviewCommentDTO:
    """A Bitbucket anchor: ``line`` is a file line number qualified by ``lineType``."""

    path: str
    line: int
    body: str
    lineType: str = "CONTEXT"


@dataclass
class GitLabReviewCommentDTO:
    """A GitLab diff note: the lines it spans, ``None`` for the side it omits.

    GitLab anchors a note with the line number on each side of the diff, so the
    host needs both the old and the new line for a context line, and only one of
    them for an added or removed line.
    """

    path: str
    body: str
    new_line: int | None = None
    old_line: int | None = None


@dataclass
class ReviewResponseDTO:
    general_comment: str
    comments: list[GitHubReviewCommentDTO | GiteaReviewCommentDTO | GitLabReviewCommentDTO | BitbucketReviewCommentDTO]

    @classmethod
    def from_request(
        cls,
        general_comment: str,
        comments: list[dict],
        git_host: GitProviderEnum,
    ) -> "ReviewResponseDTO":
        """Build the host-specific comment objects the git port expects."""
        match git_host:
            case GitProviderEnum.GITHUB:
                return cls(
                    general_comment=general_comment,
                    comments=[GitHubReviewCommentDTO(**comment) for comment in comments],
                )
            case GitProviderEnum.GITEA:
                return cls(
                    general_comment=general_comment,
                    comments=[GiteaReviewCommentDTO(**comment) for comment in comments],
                )
            case GitProviderEnum.GITLAB:
                return cls(
                    general_comment=general_comment,
                    comments=[GitLabReviewCommentDTO(**comment) for comment in comments],
                )
            case GitProviderEnum.BITBUCKET:
                return cls(
                    general_comment=general_comment,
                    comments=[BitbucketReviewCommentDTO(**comment) for comment in comments],
                )
            case _:
                raise UnknownGitProviderException("Unknown Git Provider")
