import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    BitBucketReviewCommentDTO,
    GiteaReviewCommentDTO,
    GithubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)

pytestmark = pytest.mark.unit


def test_create_github_response_ai_provider_dto():
    general_comment = "test comment"
    comments = [
        {"path": "test path", "line": 10, "side": "RIGHT", "body": "test body"},
        {"path": "test path 2", "line": 22, "side": "LEFT", "body": "test body 2"},
    ]

    dto = ReviewResponseDTO.from_request(
        general_comment=general_comment,
        comments=comments,
        git_host=GitProviderEnum.GITHUB,
    )

    assert isinstance(dto, ReviewResponseDTO)
    assert isinstance(dto.comments[0], GithubReviewCommentDTO)
    assert dto.general_comment == general_comment
    assert dto.comments[0].line == 10
    assert dto.comments[1].side == "LEFT"
    assert dto.comments[1].path == "test path 2"


def test_github_response_defaults_to_the_new_side():
    dto = ReviewResponseDTO.from_request(
        general_comment="c",
        comments=[{"path": "p", "line": 1, "body": "b"}],
        git_host=GitProviderEnum.GITHUB,
    )

    assert dto.comments[0].side == "RIGHT"


def test_create_gitea_response_ai_provider_dto():
    general_comment = "test comment"
    comments = [
        {"path": "test path", "old_position": 0, "new_position": 1, "body": "test body"},
        {"path": "test path 2", "old_position": 2, "new_position": 2, "body": "test body 2"},
    ]

    dto = ReviewResponseDTO.from_request(
        general_comment=general_comment,
        comments=comments,
        git_host=GitProviderEnum.GITEA,
    )

    assert isinstance(dto, ReviewResponseDTO)
    assert isinstance(dto.comments[0], GiteaReviewCommentDTO)
    assert dto.general_comment == general_comment
    assert dto.comments[1].path == "test path 2"
    assert dto.comments[0].new_position == 1


def test_create_bitbucket_response_ai_provider_dto():
    general_comment = "test comment"
    comments = [
        {"path": "test path", "lineType": "ADDED", "line": 1, "body": "test body"},
        {"path": "test path 2", "lineType": "REMOVED", "line": 2, "body": "test body 2"},
    ]

    dto = ReviewResponseDTO.from_request(
        general_comment=general_comment,
        comments=comments,
        git_host=GitProviderEnum.BITBUCKET,
    )

    assert isinstance(dto, ReviewResponseDTO)
    assert isinstance(dto.comments[0], BitBucketReviewCommentDTO)
    assert dto.general_comment == general_comment
    assert dto.comments[1].path == "test path 2"
    assert dto.comments[0].lineType == "ADDED"
    assert dto.comments[1].line == 2


def test_create_unknown_response_ai_provider_dto():
    with pytest.raises(UnknownGitProviderException) as exc_info:
        ReviewResponseDTO.from_request(
            general_comment="",
            comments=[],
            git_host="unknown",  # type: ignore[arg-type]
        )

    assert "Unknown Git Provider" in str(exc_info.value)
