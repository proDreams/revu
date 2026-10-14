"""One review, several destinations."""

from unittest.mock import AsyncMock, call

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GitHubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.publishers.composite_publisher import (
    CompositePublisher,
    combine_publishers,
)

pytestmark = pytest.mark.unit

REVIEW = ReviewResponseDTO(
    general_comment="итог",
    comments=[GitHubReviewCommentDTO(path="a.py", line=4, side="RIGHT", body="тут")],
)


async def test_every_publisher_gets_the_same_review():
    first, second = AsyncMock(), AsyncMock()

    await CompositePublisher(first, second).send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=REVIEW,
        index=7,
    )

    for publisher in (first, second):
        publisher.send_inline.assert_awaited_once_with(sha="abc", repo_owner="owner/repo", review=REVIEW, index=7)


async def test_a_comment_reaches_every_publisher_too():
    first, second = AsyncMock(), AsyncMock()

    await CompositePublisher(first, second).send_comment(repo_owner="owner/repo", review="итог", index=7)

    assert (
        first.send_comment.await_args_list
        == second.send_comment.await_args_list
        == [call(repo_owner="owner/repo", review="итог", index=7)]
    )


def test_one_destination_needs_no_wrapper():
    publisher = AsyncMock()

    assert combine_publishers(publisher) is publisher


def test_several_destinations_become_one_publisher():
    combined = combine_publishers(AsyncMock(), AsyncMock())

    assert isinstance(combined, CompositePublisher)
