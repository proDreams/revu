from dataclasses import dataclass

from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)


@dataclass
class GithubReviewCommentDTO:
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
class BitBucketReviewCommentDTO:
    """A Bitbucket anchor: ``line`` is a file line number qualified by ``lineType``."""

    path: str
    line: int
    body: str
    lineType: str = "CONTEXT"


@dataclass
class ReviewResponseDTO:
    general_comment: str
    comments: list[GithubReviewCommentDTO | GiteaReviewCommentDTO | BitBucketReviewCommentDTO]

    @classmethod
    def from_request(cls, general_comment: str, comments: list[dict], git_provider: str) -> "ReviewResponseDTO":
        match git_provider:
            case "github":
                return cls(
                    general_comment=general_comment,
                    comments=[GithubReviewCommentDTO(**comment) for comment in comments],
                )
            case "gitea":
                return cls(
                    general_comment=general_comment,
                    comments=[GiteaReviewCommentDTO(**comment) for comment in comments],
                )
            case "bitbucket":
                return cls(
                    general_comment=general_comment,
                    comments=[BitBucketReviewCommentDTO(**comment) for comment in comments],
                )
            case _:
                raise UnknownGitProviderException("Unknown Git Provider")
