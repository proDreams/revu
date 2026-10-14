"""Signing ReVu's own comments, so it never mistakes a person's for its own."""

import pytest

from revu.application.entities.review_marker import (
    BADGE,
    INLINE_BADGE,
    MARKER,
    clean,
    header,
    is_marked,
    mark,
    sign_inline,
)

pytestmark = pytest.mark.unit


def test_a_marked_body_is_recognised():
    assert is_marked(mark("обычный комментарий")) is True


def test_an_unmarked_body_is_somebody_elses():
    """The whole point: a comment by the account ReVu runs on is not ReVu's."""
    assert is_marked("WIP, не смотрите пока") is False


def test_the_marker_survives_trailing_whitespace():
    assert is_marked(f"текст\n{MARKER}\n  ") is True


def test_a_quote_of_a_marked_comment_is_not_marked():
    """A reply quotes our text; the marker must not be at the end of it."""
    assert is_marked(f"> {MARKER}\n\nсогласен") is False


def test_marking_is_idempotent_enough_for_a_retry():
    once = mark("текст")

    assert is_marked(once) is True
    assert clean(mark(once)) == "текст"


def test_marking_an_empty_body_still_leaves_a_signature():
    assert is_marked(mark("   ")) is True


def test_cleaning_removes_the_signature():
    assert clean(mark("поправь импорты")) == "поправь импорты"


def test_cleaning_removes_the_badge_of_an_inline_comment():
    assert clean(sign_inline("поправь импорты")) == "поправь импорты"


def test_cleaning_removes_the_header_and_the_progress_line():
    body = mark(f"{header(re_review=True)}\n📊 Из прошлых замечаний исправлено: 1 из 2.\n\nитог ревью")

    assert clean(body) == "итог ревью"


def test_cleaning_keeps_the_review_text_intact():
    text = "Первая строка\n\n- пункт\n- пункт"

    assert clean(mark(text)) == text


def test_cleaning_a_body_that_was_never_marked_leaves_it_alone():
    assert clean("просто комментарий") == "просто комментарий"


def test_the_header_says_which_review_it_is():
    assert header(re_review=False) == BADGE
    assert "повторное ревью" in header(re_review=True)


def test_the_inline_badge_names_revu():
    assert sign_inline("тело").startswith(INLINE_BADGE)
