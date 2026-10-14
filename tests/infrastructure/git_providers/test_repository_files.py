"""Reading bytes off a host that may not answer in the encoding it promised."""

import pytest

from revu.infrastructure.git_providers.repository_files import (
    MAX_FILE_CHARS,
    decode,
    too_large,
)

pytestmark = pytest.mark.unit


def test_bytes_are_decoded():
    assert decode("привет".encode()) == "привет"


def test_broken_encoding_is_replaced_instead_of_raising():
    """A review must not fail because one file is not valid UTF-8."""
    assert decode(b"caf\xe9") == "caf\ufffd"


def test_text_passes_through():
    assert decode("already text") == "already text"


@pytest.mark.parametrize("value", [None, 42, ["x"], object()])
def test_anything_else_is_empty_text(value):
    assert decode(value) == ""


def test_a_file_past_the_limit_is_recognised():
    assert too_large("x" * MAX_FILE_CHARS) is False
    assert too_large("x" * (MAX_FILE_CHARS + 1)) is True
