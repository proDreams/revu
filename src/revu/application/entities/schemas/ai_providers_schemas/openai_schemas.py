from typing import Literal

from pydantic import BaseModel, field_validator


class GitHubReviewComment(BaseModel):
    """An inline GitHub comment anchored by file line number and side.

    ``side`` is ``RIGHT`` for the new version of the file and ``LEFT`` for the
    old one. This replaces the deprecated ``position``, which was an offset from
    the first hunk header rather than a line number and therefore anchored
    comments incorrectly for any hunk that does not start at line 1.
    """

    path: str
    line: int
    body: str
    side: Literal["LEFT", "RIGHT"] = "RIGHT"

    @field_validator("side", mode="before")
    @classmethod
    def _normalize_side(cls, value: object) -> object:
        """Tolerate lowercase or empty sides from providers without a schema."""
        normalized = str(value).strip().upper() if value is not None else ""
        return normalized or "RIGHT"


class GiteaReviewComment(BaseModel):
    path: str
    old_position: int
    new_position: int
    body: str


class BitbucketReviewComment(BaseModel):
    path: str
    line: int
    body: str
    lineType: Literal["ADDED", "REMOVED", "CONTEXT"] = "CONTEXT"

    @field_validator("lineType", mode="before")
    @classmethod
    def _normalize_line_type(cls, value: object) -> object:
        normalized = str(value).strip().upper() if value is not None else ""
        return normalized or "CONTEXT"


class ReviewResponse(BaseModel):
    general_comment: str


class GithubReviewResponse(ReviewResponse):
    comments: list[GitHubReviewComment]


class GiteaReviewResponse(ReviewResponse):
    comments: list[GiteaReviewComment]


class BitbucketReviewResponse(ReviewResponse):
    comments: list[BitbucketReviewComment]
