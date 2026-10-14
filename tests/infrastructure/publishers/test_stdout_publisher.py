"""Publishing into a job log: what a CI reader actually sees."""

import io

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.publishers.stdout_publisher import StdoutPublisher

pytestmark = pytest.mark.unit


@pytest.fixture
def output():
    return io.StringIO()


@pytest.fixture
def publisher(output):
    return StdoutPublisher(stream=output)


async def test_a_comment_is_printed_as_it_would_be_posted(publisher, output):
    await publisher.send_comment(repo_owner="owner/repo", review="🤖 **ReVu**\n\nВсё хорошо", index=7)

    assert output.getvalue() == "🤖 **ReVu**\n\nВсё хорошо\n"


async def test_an_inline_review_prints_the_summary_and_every_line(publisher, output):
    review = ReviewResponseDTO(
        general_comment="🤖 **ReVu**\n\nИтог",
        comments=[
            GitHubReviewCommentDTO(path="app.py", line=12, side="RIGHT", body="Тут гонка"),
            GitHubReviewCommentDTO(path="other.py", line=3, side="RIGHT", body="И тут"),
        ],
    )

    await publisher.send_inline(sha="abc", repo_owner="owner/repo", review=review, index=7)

    printed = output.getvalue()
    assert "Итог" in printed
    assert "**Замечания по строкам:**" in printed
    assert "- `app.py:12` — Тут гонка" in printed
    assert "- `other.py:3` — И тут" in printed


async def test_a_review_without_inline_comments_prints_no_list(publisher, output):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=ReviewResponseDTO(general_comment="только итог", comments=[]),
        index=7,
    )

    assert "Замечания по строкам" not in output.getvalue()


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        (GitHubReviewCommentDTO(path="a.py", line=4, side="RIGHT", body="x"), "- `a.py:4` — x"),
        # GitLab addresses a line on each side of the diff; the new one is the line
        # a reader of the log is looking at.
        (GitLabReviewCommentDTO(path="b.py", new_line=9, body="y"), "- `b.py:9` — y"),
        (GitLabReviewCommentDTO(path="c.py", old_line=2, body="z"), "- `c.py:2` — z"),
        # Gitea speaks in diff positions, which say nothing without the diff.
        (GiteaReviewCommentDTO(path="d.py", old_position=0, new_position=5, body="w"), "- `d.py` — w"),
    ],
)
async def test_the_line_is_read_from_whichever_field_the_host_uses(publisher, output, comment, expected):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=ReviewResponseDTO(general_comment="итог", comments=[comment]),
        index=7,
    )

    assert expected in output.getvalue()


async def test_a_multi_line_comment_stays_one_log_line(publisher, output):
    review = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="первая\nвторая\n\nтретья")],
    )

    await publisher.send_inline(sha="abc", repo_owner="owner/repo", review=review, index=7)

    assert "- `a.py:1` — первая вторая третья" in output.getvalue()


async def test_the_default_destination_is_stdout(capsys):
    await StdoutPublisher().send_comment(repo_owner="owner/repo", review="привет", index=7)

    assert capsys.readouterr().out == "привет\n"


async def test_a_comment_without_the_expected_fields_is_still_printed(publisher, output):
    """A publisher must not be the place where a review dies."""

    class Odd:
        body = "тело"

    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=ReviewResponseDTO(general_comment="итог", comments=[Odd()]),  # type: ignore[list-item]
        index=7,
    )

    assert "- `?` — тело" in output.getvalue()


async def test_the_invisible_signature_is_not_printed_as_if_it_were_text(publisher, output):
    """The marker is how ReVu recognises its own comment; a reader does not need it."""
    review = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="🤖 ReVu: тут\n\n<!-- revu -->")],
    )

    await publisher.send_inline(sha="abc", repo_owner="owner/repo", review=review, index=7)

    assert "- `a.py:1` — тут" in output.getvalue()
