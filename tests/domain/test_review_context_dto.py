"""The comments a pull request already carries, split into findings and talk."""

import pytest

from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)

pytestmark = pytest.mark.unit


def _comment(author: str, body: str, is_revu: bool = False, **overrides) -> PreviousCommentDTO:
    return PreviousCommentDTO(author=author, body=body, is_revu=is_revu, **overrides)


def test_an_empty_context_has_nothing():
    context = ReviewContextDTO()

    assert context.findings == ()
    assert context.discussion == ()
    assert context.has_findings is False


def test_revu_comments_are_findings_and_the_rest_is_discussion():
    ours = _comment("revu", "поправь", is_revu=True)
    theirs = _comment("ivan", "не надо")
    context = ReviewContextDTO(comments=(ours, theirs))

    assert context.findings == (ours,)
    assert context.discussion == (theirs,)
    assert context.has_findings is True


def test_discussion_alone_is_not_a_review_history():
    """A pull request nobody reviewed yet is still a first review."""
    context = ReviewContextDTO(comments=(_comment("ivan", "привет"),))

    assert context.has_findings is False
    assert context.discussion == context.comments


def test_a_comment_can_carry_its_place_and_state():
    comment = _comment("revu", "тут", is_revu=True, path="app.py", line=12, resolved=True)

    assert (comment.path, comment.line, comment.resolved) == ("app.py", 12, True)
