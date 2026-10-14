from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


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


class GitLabReviewComment(BaseModel):
    """An inline GitLab diff note, anchored by the lines it spans.

    GitLab positions a note with the line number on each side of the diff: an
    added line carries only ``new_line``, a removed line only ``old_line``, and a
    context line both. A comment with neither cannot be positioned at all.
    """

    path: str
    body: str
    new_line: int | None = None
    old_line: int | None = None

    @field_validator("new_line", "old_line", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        """Providers without a schema like to answer an inapplicable line as ""."""
        if value is None or (isinstance(value, str) and not value.strip()):
            return None

        return value

    @model_validator(mode="after")
    def _require_a_line(self) -> "GitLabReviewComment":
        if self.new_line is None and self.old_line is None:
            raise ValueError("a GitLab comment needs new_line, old_line or both")

        return self


class ReviewResponse(BaseModel):
    general_comment: str


class GithubReviewResponse(ReviewResponse):
    comments: list[GitHubReviewComment]


class GiteaReviewResponse(ReviewResponse):
    comments: list[GiteaReviewComment]


class BitbucketReviewResponse(ReviewResponse):
    comments: list[BitbucketReviewComment]


class GitlabReviewResponse(ReviewResponse):
    comments: list[GitLabReviewComment]


# The shapes differ only in their comment type, which is exactly what the git host
# decides; this alias keeps `.comments` visible to the type checker.
InlineReviewResponse = GithubReviewResponse | GiteaReviewResponse | BitbucketReviewResponse | GitlabReviewResponse
