"""The review scenario on its own, with its source and destination passed in.

The webhook path is covered through the service; what matters here is that the
runner does not care who provides the change or where the answer goes — which is
what lets a CI job read a local checkout and still publish into the host.
"""

from unittest.mock import AsyncMock

import pytest

from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.application.services.review_runner import (
    ReviewRequest,
    ReviewRunner,
)
from revu.domain.entities.dto.ai_provider_dto import (
    FindingStatusEnum,
    PreviousFindingDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.dto.code_context_dto import (
    CodeContextDTO,
    ContextEntryDTO,
    ContextStatsDTO,
)
from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from tests.conftest import make_connection

pytestmark = pytest.mark.unit

DIFF = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,2 @@
 context
-old line
+new line
"""

COMMIT_SHA = "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"

REQUEST = ReviewRequest(
    repo="owner/repo",
    number=7,
    title="Add feature",
    body="Implements it",
    revision=COMMIT_SHA,
)


@pytest.fixture
def context_builder():
    builder = AsyncMock()
    builder.build.return_value = CodeContextDTO(
        entries=(ContextEntryDTO(kind="symbol", path="app.py", title="run", text="def run(): pass"),),
        stats=ContextStatsDTO(depth="deep", changed_files=1, chars=24),
    )

    return builder


@pytest.fixture
def runner(context_builder):
    return ReviewRunner(context_builder=context_builder)


@pytest.fixture
def reader():
    port = AsyncMock()
    port.fetch_diff.return_value = DIFF
    port.fetch_review_context.return_value = None

    return port


@pytest.fixture
def publisher():
    return AsyncMock()


@pytest.fixture
def ai_port():
    port = AsyncMock()
    port.get_comment_response.return_value = "comment review"
    port.get_inline_response.return_value = ReviewResponseDTO(general_comment="inline review", comments=[])

    return port


async def test_the_source_and_the_destination_can_be_different_objects(
    runner,
    reader,
    publisher,
    ai_port,
    context_builder,
):
    """A CI job reads its own checkout and writes into the host — the whole point."""
    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(),
        request=REQUEST,
    )

    reader.fetch_diff.assert_awaited_once_with(repo="owner/repo", index=7)
    # Reading happens on the reader, publishing on the publisher: neither is asked
    # to do the other's job, which is what the split protocols guarantee.
    reader.send_comment.assert_not_awaited()
    reader.send_inline.assert_not_awaited()
    publisher.fetch_diff.assert_not_awaited()
    publisher.send_inline.assert_awaited_once()
    assert outcome.published == 0


async def test_the_runner_reads_the_context_from_the_same_source(runner, reader, publisher, ai_port, context_builder):
    await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(context_depth="deep"),
        request=REQUEST,
    )

    # The builder was handed the reader, not the publisher.
    assert context_builder.build.await_args.args[0] is reader


async def test_comment_mode_publishes_exactly_one_comment(runner, reader, publisher, ai_port, context_builder):
    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.COMMENT),
        request=REQUEST,
    )

    publisher.send_comment.assert_awaited_once()
    published = publisher.send_comment.await_args.kwargs["review"]
    assert "comment review" in published
    assert (outcome.mode, outcome.published, outcome.dropped, outcome.re_review) == (
        ReviewModeEnum.COMMENT,
        1,
        0,
        False,
    )


async def test_inline_mode_reports_how_many_comments_were_published(
    runner,
    reader,
    publisher,
    ai_port,
    context_builder,
):
    from revu.domain.entities.dto.ai_provider_dto import GitHubReviewCommentDTO

    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="inline review",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="careful")],
    )

    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.INLINE),
        request=REQUEST,
    )

    assert (outcome.published, outcome.dropped) == (1, 0)
    assert outcome.mode is ReviewModeEnum.INLINE


async def test_a_follow_up_review_is_reported_as_one(runner, reader, publisher, ai_port, context_builder):
    reader.fetch_review_context.return_value = ReviewContextDTO(
        comments=[PreviousCommentDTO(author="revu", body="<!-- revu --> earlier", is_revu=True)],
    )
    ai_port.get_comment_response.return_value = "second look"

    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.COMMENT),
        request=REQUEST,
    )

    assert outcome.re_review is True


async def test_the_outcome_carries_what_the_context_cost(runner, reader, publisher, ai_port, context_builder):
    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.COMMENT),
        request=REQUEST,
    )

    assert outcome.code_context.entries[0].text == "def run(): pass"
    assert outcome.code_context.stats.chars == 24


async def test_other_people_comments_can_be_kept_away_from_the_provider(
    runner,
    reader,
    publisher,
    ai_port,
    context_builder,
):
    """The flag is a connection setting, and the runner is what honours it."""
    reader.fetch_review_context.return_value = ReviewContextDTO(
        comments=[
            PreviousCommentDTO(author="someone", body="a human opinion", is_revu=False),
        ],
    )

    await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.COMMENT, include_pr_discussion=False),
        request=REQUEST,
    )

    task = ai_port.get_comment_response.await_args.args[0]
    assert task.previous_review is not None
    assert [comment.body for comment in task.previous_review.comments] == []


async def test_the_progress_line_still_counts_only_the_findings(runner, reader, publisher, ai_port, context_builder):
    reader.fetch_review_context.return_value = ReviewContextDTO(
        comments=[
            PreviousCommentDTO(author="revu", body="<!-- revu --> first", is_revu=True),
            PreviousCommentDTO(author="revu", body="<!-- revu --> second", is_revu=True),
        ],
    )
    ai_port.get_comment_response.return_value = "second look"
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="second look",
        comments=[],
        previous_findings=[PreviousFindingDTO(summary="fixed", status=FindingStatusEnum.FIXED)],
    )

    outcome = await runner.run(
        reader=reader,
        publisher=publisher,
        ai_port=ai_port,
        config=make_connection(review_mode=ReviewModeEnum.INLINE),
        request=REQUEST,
    )

    published = publisher.send_inline.await_args.kwargs["review"]
    assert "Из прошлых замечаний исправлено: 1 из 2" in published.general_comment
    assert outcome.re_review is True


async def test_the_wait_for_the_model_is_visible_in_the_log(runner, reader, publisher, ai_port, caplog):
    """The longest silence in a review log is the model thinking; name it.

    Without this line the log ends at the request and looks stuck: a response whose
    headers arrive in under a second can still be minutes of generation behind it.
    """
    with caplog.at_level("INFO"):
        await runner.run(
            reader=reader,
            publisher=publisher,
            ai_port=ai_port,
            config=make_connection(review_mode=ReviewModeEnum.INLINE),
            request=REQUEST,
        )

    assert f"asking the model about {REQUEST.repo}#{REQUEST.number}" in caplog.text
