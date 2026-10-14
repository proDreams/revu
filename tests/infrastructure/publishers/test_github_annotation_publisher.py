"""A review as annotations the runner turns into marks on the diff."""

import io

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.publishers.github_annotation_publisher import (
    GitHubAnnotationPublisher,
    escape_data,
    escape_property,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def output():
    return io.StringIO()


@pytest.fixture
def publisher(output):
    return GitHubAnnotationPublisher(stream=output)


def review_with(*comments) -> ReviewResponseDTO:
    return ReviewResponseDTO(general_comment="итог", comments=list(comments))


async def test_a_comment_becomes_a_warning_on_its_line(publisher, output):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(GitHubReviewCommentDTO(path="app.py", line=12, side="RIGHT", body="Тут гонка")),
        index=7,
    )

    assert output.getvalue() == "::warning file=app.py,line=12,endLine=12,title=ReVu::Тут гонка\n"


async def test_every_comment_gets_its_own_annotation(publisher, output):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(
            GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="первое"),
            GitHubReviewCommentDTO(path="b.py", line=2, side="RIGHT", body="второе"),
        ),
        index=7,
    )

    assert len(output.getvalue().strip().splitlines()) == 2


async def test_a_general_comment_has_nothing_to_annotate(publisher, output):
    await publisher.send_comment(repo_owner="owner/repo", review="итог", index=7)

    assert output.getvalue() == ""


async def test_a_newline_cannot_end_the_command(publisher, output):
    """A review comment with a blank line would otherwise become plain log output."""
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="первая\n\nвторая")),
        index=7,
    )

    printed = output.getvalue()
    assert printed.count("\n") == 1
    assert "первая%0A%0Aвторая" in printed


async def test_a_path_with_a_comma_cannot_break_the_properties(publisher, output):
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(GitHubReviewCommentDTO(path="a,b.py", line=1, side="RIGHT", body="x")),
        index=7,
    )

    assert "file=a%2Cb.py" in output.getvalue()


@pytest.mark.parametrize(
    ("comment", "expected"),
    [
        (GitLabReviewCommentDTO(path="a.py", new_line=9, body="x"), "file=a.py,line=9,endLine=9"),
        # Gitea positions say nothing about a line, so the file is all there is.
        (GiteaReviewCommentDTO(path="a.py", old_position=0, new_position=5, body="x"), "file=a.py,title=ReVu"),
    ],
)
async def test_the_line_comes_from_whichever_field_the_host_uses(publisher, output, comment, expected):
    await publisher.send_inline(sha="abc", repo_owner="owner/repo", review=review_with(comment), index=7)

    assert expected in output.getvalue()


async def test_the_signature_is_cleaned_out_of_the_annotation(publisher, output):
    """An annotation is plain text, so an invisible marker would become visible."""
    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(
            GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="🤖 ReVu: тут\n\n<!-- revu -->")
        ),
        index=7,
    )

    assert output.getvalue() == "::warning file=a.py,line=1,endLine=1,title=ReVu::тут\n"


async def test_a_comment_without_a_file_is_skipped(publisher, output):
    class Odd:
        body = "тело"

    await publisher.send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(Odd()),  # type: ignore[arg-type]
        index=7,
    )

    assert output.getvalue() == ""


async def test_the_default_destination_is_stdout(capsys):
    await GitHubAnnotationPublisher().send_inline(
        sha="abc",
        repo_owner="owner/repo",
        review=review_with(GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="x")),
        index=7,
    )

    assert capsys.readouterr().out.startswith("::warning ")


@pytest.mark.parametrize(
    ("raw", "data", "prop"),
    [
        ("100%", "100%25", "100%25"),
        ("a:b", "a:b", "a%3Ab"),
        ("a,b", "a,b", "a%2Cb"),
        ("a\r\nb", "a%0D%0Ab", "a%0D%0Ab"),
    ],
)
def test_escaping_follows_the_workflow_command_rules(raw, data, prop):
    assert escape_data(raw) == data
    assert escape_property(raw) == prop
