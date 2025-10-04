from dataclasses import dataclass


@dataclass
class GithubReviewCommentDTO:
    path: str
    position: int
    body: str


@dataclass
class GiteaReviewCommentDTO:
    path: str
    old_position: int
    new_position: int
    body: str


@dataclass
class ReviewResponseDTO:
    general_comment: str
    comments: list[GithubReviewCommentDTO | GiteaReviewCommentDTO]

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
            case _:
                raise NotImplementedError
