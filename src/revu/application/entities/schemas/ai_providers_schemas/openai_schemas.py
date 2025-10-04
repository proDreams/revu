from pydantic import BaseModel


class GitHubReviewComment(BaseModel):
    path: str
    position: int
    body: str


class GiteaReviewComment(BaseModel):
    path: str
    old_position: int
    new_position: int
    body: str


class ReviewResponse(BaseModel):
    general_comment: str


class GithubReviewResponse(ReviewResponse):
    comments: list[GitHubReviewComment]


class GiteaReviewResponse(ReviewResponse):
    comments: list[GiteaReviewComment]
