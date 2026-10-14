"""A review as a report GitLab shows in the merge request widget.

The point of this destination is that it writes a file: no token is asked for, no
note is created, and a job whose token may not comment still gets its findings in
front of the person merging.
"""

import hashlib
import json
from pathlib import Path

import pytest

from revu.domain.entities.dto.ai_provider_dto import (
    GiteaReviewCommentDTO,
    GitHubReviewCommentDTO,
    GitLabReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.infrastructure.publishers.gitlab_codequality_publisher import (
    CHECK_NAME,
    SEVERITY,
    GitLabCodeQualityPublisher,
)

pytestmark = pytest.mark.unit


def review_with(*comments) -> ReviewResponseDTO:
    return ReviewResponseDTO(general_comment="итог", comments=list(comments))


@pytest.fixture
def report(tmp_path: Path) -> Path:
    return tmp_path / "reports" / "revu-codequality.json"


@pytest.fixture
def publisher(report):
    return GitLabCodeQualityPublisher(path=report)


def read(report: Path) -> list[dict]:
    return json.loads(report.read_text(encoding="utf-8"))


async def test_a_comment_becomes_a_finding_on_its_line(publisher, report):
    await publisher.send_inline(
        sha="abc",
        repo_owner="group/project",
        review=review_with(GitHubReviewCommentDTO(path="app.py", line=12, side="RIGHT", body="Тут гонка")),
        index=7,
    )

    assert read(report) == [
        {
            "description": "Тут гонка",
            "check_name": CHECK_NAME,
            "severity": SEVERITY,
            "fingerprint": hashlib.sha1(
                b"app.py:12:\xd0\xa2\xd1\x83\xd1\x82 \xd0\xb3\xd0\xbe\xd0\xbd\xd0\xba\xd0\xb0"
            ).hexdigest(),
            "location": {"path": "app.py", "lines": {"begin": 12}},
        }
    ]


async def test_the_report_is_written_where_it_was_asked_for(publisher, report):
    """A missing file fails the job, because the artifact is declared in the config."""
    assert not report.exists()

    await publisher.send_inline(
        sha="abc",
        repo_owner="group/project",
        review=review_with(GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="x")),
        index=7,
    )

    assert report.is_file()


async def test_the_same_finding_keeps_the_same_fingerprint(publisher, report):
    """GitLab tracks a finding by its fingerprint; a changing one looks brand new."""
    comment = GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="x")
    await publisher.send_inline(sha="abc", repo_owner="r", review=review_with(comment), index=1)
    first = read(report)[0]["fingerprint"]
    await publisher.send_inline(sha="def", repo_owner="r", review=review_with(comment), index=1)

    assert read(report)[0]["fingerprint"] == first


async def test_a_different_finding_gets_a_different_fingerprint(publisher, report):
    await publisher.send_inline(
        sha="abc",
        repo_owner="r",
        review=review_with(GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="x")),
        index=1,
    )
    first = read(report)[0]["fingerprint"]
    await publisher.send_inline(
        sha="abc",
        repo_owner="r",
        review=review_with(GitHubReviewCommentDTO(path="a.py", line=2, side="RIGHT", body="x")),
        index=1,
    )

    assert read(report)[0]["fingerprint"] != first


async def test_a_comment_without_a_line_is_left_out(publisher, report, caplog):
    """A finding the report cannot place is worse than a finding it omits."""
    with caplog.at_level("INFO"):
        await publisher.send_inline(
            sha="abc",
            repo_owner="r",
            review=review_with(
                GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="первое"),
                GiteaReviewCommentDTO(path="b.py", old_position=0, new_position=5, body="второе"),
            ),
            index=1,
        )

    assert [entry["location"]["path"] for entry in read(report)] == ["a.py"]
    assert "1 of 2 comments" in caplog.text


async def test_a_comment_mode_review_still_writes_an_empty_report(publisher, report):
    await publisher.send_comment(repo_owner="group/project", review="итог", index=7)

    assert read(report) == []


@pytest.mark.parametrize(
    "comment",
    [
        GitLabReviewCommentDTO(path="a.py", new_line=9, body="x"),
        GitLabReviewCommentDTO(path="a.py", old_line=3, body="x"),
    ],
)
async def test_the_line_comes_from_whichever_field_the_host_uses(publisher, report, comment):
    await publisher.send_inline(sha="abc", repo_owner="r", review=review_with(comment), index=1)

    assert read(report)[0]["location"]["lines"]["begin"] in {9, 3}


async def test_a_zero_line_is_not_a_line(publisher, report):
    await publisher.send_inline(
        sha="abc",
        repo_owner="r",
        review=review_with(GitLabReviewCommentDTO(path="a.py", new_line=0, old_line=0, body="x")),
        index=1,
    )

    assert read(report) == []


async def test_the_signature_is_cleaned_out_of_the_description(publisher, report):
    """GitLab renders a description as text, so an invisible marker would show."""
    await publisher.send_inline(
        sha="abc",
        repo_owner="r",
        review=review_with(
            GitHubReviewCommentDTO(path="a.py", line=1, side="RIGHT", body="🤖 ReVu: тут\n\n<!-- revu -->")
        ),
        index=1,
    )

    assert read(report)[0]["description"] == "тут"
