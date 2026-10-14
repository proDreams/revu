from dataclasses import dataclass

from revu.application.entities.enums.finding_status_enums import (
    FindingStatusEnum,
    to_finding_status,
)
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
class PreviousFindingDTO:
    """What became of one finding from an earlier review."""

    summary: str
    status: FindingStatusEnum = FindingStatusEnum.REMAINING

    def __post_init__(self) -> None:
        """Accept a plain string too: ports and tests build these from raw JSON."""
        if not isinstance(self.status, FindingStatusEnum):
            self.status = to_finding_status(self.status)

    @property
    def is_fixed(self) -> bool:
        return self.status is FindingStatusEnum.FIXED


@dataclass
class ReviewResponseDTO:
    general_comment: str
    comments: list[GitHubReviewCommentDTO | GiteaReviewCommentDTO | GitLabReviewCommentDTO | BitbucketReviewCommentDTO]
    #: Empty on a first review; a re-review reports the fate of every earlier finding.
    previous_findings: list[PreviousFindingDTO] | None = None

    @classmethod
    def from_request(
        cls,
        general_comment: str,
        comments: list[dict],
        git_host: GitProviderEnum,
        previous_findings: list[dict] | None = None,
    ) -> "ReviewResponseDTO":
        """Build the host-specific comment objects the git port expects."""
        findings = [PreviousFindingDTO(**finding) for finding in previous_findings or []]

        match git_host:
            case GitProviderEnum.GITHUB:
                return cls(
                    general_comment=general_comment,
                    comments=[GitHubReviewCommentDTO(**comment) for comment in comments],
                    previous_findings=findings,
                )
            case GitProviderEnum.GITEA:
                return cls(
                    general_comment=general_comment,
                    comments=[GiteaReviewCommentDTO(**comment) for comment in comments],
                    previous_findings=findings,
                )
            case GitProviderEnum.GITLAB:
                return cls(
                    general_comment=general_comment,
                    comments=[GitLabReviewCommentDTO(**comment) for comment in comments],
                    previous_findings=findings,
                )
            case GitProviderEnum.BITBUCKET:
                return cls(
                    general_comment=general_comment,
                    comments=[BitbucketReviewCommentDTO(**comment) for comment in comments],
                    previous_findings=findings,
                )
            case _:
                raise UnknownGitProviderException("Unknown Git Provider")
