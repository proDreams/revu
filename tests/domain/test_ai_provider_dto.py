import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    GithubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)

pytestmark = pytest.mark.unit


def test_create_github_response_ai_provider_dto():
    general_comment = "test comment"
    comments = [
        {"path": "test path", "position": 0, "body": "test body"},
        {"path": "test path 2", "position": 2, "body": "test body 2"},
    ]
    git_provider = "github"

    dto = ReviewResponseDTO.from_request(general_comment=general_comment, comments=comments, git_provider=git_provider)

    assert isinstance(dto, ReviewResponseDTO)
    assert isinstance(dto.comments[0], GithubReviewCommentDTO)
    assert dto.general_comment == general_comment
    assert dto.comments[1].path == "test path 2"


def test_create_gitea_response_ai_provider_dto():
    general_comment = "test comment"
    comments = [
        {"path": "test path", "old_position": 0, "new_position": 1, "body": "test body"},
        {"path": "test path 2", "old_position": 2, "new_position": 2, "body": "test body 2"},
    ]
    git_provider = "gitea"

    dto = ReviewResponseDTO.from_request(general_comment=general_comment, comments=comments, git_provider=git_provider)

    assert isinstance(dto, ReviewResponseDTO)
    assert isinstance(dto.comments[0], GiteaReviewCommentDTO)
    assert dto.general_comment == general_comment
    assert dto.comments[1].path == "test path 2"
    assert dto.comments[0].new_position == 1


def test_create_unknown_response_ai_provider_dto():
    general_comment = ""
    comments = []
    git_provider = "unknown"

    with pytest.raises(UnknownGitProviderException) as exc_info:
        ReviewResponseDTO.from_request(general_comment=general_comment, comments=comments, git_provider=git_provider)

    assert "Unknown Git Provider" in str(exc_info.value)
