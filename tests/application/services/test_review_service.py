import asyncio
from unittest.mock import AsyncMock

import pytest

from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.application.entities.exceptions.review_service_exceptions import (
    ReviewModeException,
)
from revu.application.entities.review_marker import MARKER, is_marked
from revu.application.entities.tenant import GitConnection, TenantContext
from revu.application.services.review_service import ReviewService
from revu.domain.entities.dto.ai_provider_dto import (
    PreviousFindingDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
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


def make_event() -> PullRequestEventDTO:
    return PullRequestEventDTO(
        action=PullRequestActionEnum.OPENED,
        repo_full_name="owner/repo",
        pr_number=7,
        pr_title="Add feature",
        commit_sha=COMMIT_SHA,
        pr_body="Implements it",
    )


@pytest.fixture
def ai_port():
    port = AsyncMock()
    port.get_comment_response.return_value = "comment review"
    port.get_inline_response.return_value = ReviewResponseDTO(general_comment="inline review", comments=[])

    return port


@pytest.fixture
def git_port():
    port = AsyncMock()
    port.fetch_diff.return_value = DIFF

    return port


@pytest.fixture
def service():
    return ReviewService()


def make_tenant(ai_port, git_port, **connection) -> TenantContext:
    return TenantContext(
        connection=GitConnection.build(config=make_connection(**connection), port=git_port),
        ai_port=ai_port,
    )


async def test_comment_mode_sends_one_comment(service, ai_port, git_port):
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.COMMENT)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_comment.await_args.kwargs["review"]
    assert published.startswith("🤖 **ReVu**")
    assert published.endswith(MARKER)
    assert "comment review" in published
    git_port.send_inline.assert_not_awaited()

    task = ai_port.get_comment_response.await_args.args[0]
    assert task.diff == DIFF
    assert task.git_host == GitProviderEnum.GITHUB
    assert task.pr_title == "Add feature"
    assert task.pr_body == "Implements it"


async def test_inline_mode_sends_the_annotated_diff(service, ai_port, git_port):
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    git_port.send_inline.assert_awaited_once()
    git_port.send_comment.assert_not_awaited()

    task = ai_port.get_inline_response.await_args.args[0]
    assert "+ [2] new line" in task.diff
    assert "- [2] old line" in task.diff
    assert "  [1->1] context" in task.diff

    assert git_port.send_inline.await_args.kwargs["sha"] == COMMIT_SHA


async def test_the_connection_review_mode_is_used(service, ai_port, git_port):
    """The mode comes from the connection, not from a global setting."""
    comment_tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.COMMENT)
    inline_tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=comment_tenant, webhook_data=make_event())
    await service.process_webhook(tenant=inline_tenant, webhook_data=make_event())

    ai_port.get_comment_response.assert_awaited_once()
    ai_port.get_inline_response.assert_awaited_once()


async def test_the_connection_system_prompt_travels_with_the_task(service, ai_port, git_port):
    tenant = make_tenant(ai_port, git_port, system_prompt="connection prompt")

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert ai_port.get_inline_response.await_args.args[0].system_prompt == "connection prompt"


async def test_the_connection_host_selects_the_output_format(service, ai_port, git_port):
    tenant = make_tenant(ai_port, git_port, host=GitProviderEnum.BITBUCKET)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert ai_port.get_inline_response.await_args.args[0].git_host == GitProviderEnum.BITBUCKET


async def test_an_unknown_review_mode_is_reported(service, ai_port, git_port):
    """Unreachable through the configuration, but the guard must still hold."""
    tenant = make_tenant(ai_port, git_port, review_mode="bogus")  # type: ignore[arg-type]

    with pytest.raises(ReviewModeException) as exc_info:
        await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert "Unknown review mode" in str(exc_info.value)


async def test_reviews_of_one_connection_are_bounded(service, ai_port):
    """A burst of pushes must not start an unlimited number of reviews."""
    running = 0
    max_running = 0
    git_port = AsyncMock()

    async def slow_fetch_diff(*args, **kwargs) -> str:
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0)
        running -= 1
        return DIFF

    git_port.fetch_diff.side_effect = slow_fetch_diff
    tenant = make_tenant(ai_port, git_port, max_concurrent_reviews=1)

    await asyncio.gather(*(service.process_webhook(tenant=tenant, webhook_data=make_event()) for _ in range(5)))

    assert max_running == 1
    assert git_port.fetch_diff.await_count == 5


async def test_connections_do_not_block_each_other(service, ai_port):
    """The budget is per connection, so one noisy repo cannot starve the rest."""
    running = 0
    max_running = 0

    def slow_port():
        port = AsyncMock()

        async def slow_fetch_diff(*args, **kwargs) -> str:
            nonlocal running, max_running
            running += 1
            max_running = max(max_running, running)
            await asyncio.sleep(0)
            running -= 1
            return DIFF

        port.fetch_diff.side_effect = slow_fetch_diff
        return port

    first = make_tenant(ai_port, slow_port(), key="gh-one", max_concurrent_reviews=1)
    second = make_tenant(ai_port, slow_port(), key="gh-two", max_concurrent_reviews=1)

    await asyncio.gather(
        service.process_webhook(tenant=first, webhook_data=make_event()),
        service.process_webhook(tenant=second, webhook_data=make_event()),
    )

    assert max_running == 2


def test_annotate_diff_marks_added_file():
    diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,1 @@
+created
"""

    annotated = ReviewService.annotate_diff(diff_text=diff)

    assert "diff --git /dev/null b/new.py" in annotated
    assert "new file mode 100644" in annotated
    assert "+ [1] created" in annotated


def test_annotate_diff_marks_removed_file():
    diff = """diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1,1 +0,0 @@
-deleted
"""

    annotated = ReviewService.annotate_diff(diff_text=diff)

    assert "deleted file mode 100644" in annotated
    assert "- [1] deleted" in annotated


def test_annotate_diff_drops_no_newline_marker():
    # unidiff strips the `\` prefix, so the marker is neither recognised as
    # context nor as a change line; it must not leak into the annotation.
    diff = """diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,1 +1,1 @@
-old
\\ No newline at end of file
+new
"""

    annotated = ReviewService.annotate_diff(diff_text=diff)

    assert "No newline at end of file" not in annotated
    assert "- [1] old" in annotated
    assert "+ [1] new" in annotated


def test_annotate_diff_passes_empty_text_through():
    assert ReviewService.annotate_diff(diff_text="") == ""


async def test_unanchored_comments_are_dropped_before_sending(service, ai_port, git_port, caplog):
    """One hallucinated line must not cost the whole review."""
    from revu.domain.entities.dto.ai_provider_dto import GitHubReviewCommentDTO

    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="inline review",
        comments=[
            GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="kept"),
            GitHubReviewCommentDTO(path="app.py", line=999, side="RIGHT", body="hallucinated"),
        ],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    with caplog.at_level("WARNING"):
        await service.process_webhook(tenant=tenant, webhook_data=make_event())

    sent = git_port.send_inline.await_args.kwargs["review"]
    assert [comment.body for comment in sent.comments] == [f"🤖 ReVu: kept\n\n{MARKER}"]
    assert "inline review" in sent.general_comment
    assert "dropped 1 of 2 inline comments for connection gh-main" in caplog.text


FINDING = PreviousCommentDTO(author="revu-bot", body="импорты лучше построчно", is_revu=True, path="app.py", line=1)
DISCUSSION = PreviousCommentDTO(author="ivan", body="не трогаем")


def _context(*comments: PreviousCommentDTO) -> ReviewContextDTO:
    return ReviewContextDTO(comments=comments)


async def test_the_previous_review_reaches_the_ai_port(service, ai_port, git_port):
    """This is the whole point: a follow-up has to see what was said before."""
    git_port.fetch_review_context.return_value = _context(FINDING, DISCUSSION)
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    task = ai_port.get_inline_response.await_args.args[0]
    assert task.previous_review is not None
    assert task.previous_review.findings == (FINDING,)
    assert task.previous_review.discussion == (DISCUSSION,)


async def test_a_first_review_carries_no_context(service, ai_port, git_port):
    git_port.fetch_review_context.return_value = None
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert ai_port.get_inline_response.await_args.args[0].previous_review is None


async def test_a_context_lookup_that_fails_does_not_lose_the_review(service, ai_port, git_port, caplog):
    """An older token without the right scope costs the context, not the review."""
    git_port.fetch_review_context.side_effect = RuntimeError("403 Forbidden")
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    with caplog.at_level("WARNING"):
        await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert ai_port.get_inline_response.await_args.args[0].previous_review is None
    assert "reviewing without them" in caplog.text
    git_port.send_inline.assert_awaited_once()


async def test_the_discussion_is_held_back_when_a_connection_asks_for_it(service, ai_port, git_port):
    """ReVu's own output is not new data; other people's comments can be."""
    git_port.fetch_review_context.return_value = _context(FINDING, DISCUSSION)
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE, include_pr_discussion=False)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    context = ai_port.get_inline_response.await_args.args[0].previous_review
    assert context is not None
    assert context.findings == (FINDING,)
    assert context.discussion == ()


async def test_the_summary_reports_how_many_findings_were_fixed(service, ai_port, git_port):
    git_port.fetch_review_context.return_value = _context(
        FINDING,
        PreviousCommentDTO(author="revu-bot", body="второе", is_revu=True),
    )
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[],
        previous_findings=[
            PreviousFindingDTO(summary="импорты", status="fixed"),
            PreviousFindingDTO(summary="второе", status="remaining"),
        ],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_inline.await_args.kwargs["review"].general_comment
    lines = published.splitlines()
    assert lines[0] == "🤖 **ReVu** · повторное ревью"
    assert lines[1] == "📊 Из прошлых замечаний исправлено: 1 из 2. Осталось: 1."
    assert "итог" in published


async def test_the_summary_says_when_everything_is_closed(service, ai_port, git_port):
    git_port.fetch_review_context.return_value = _context(FINDING)
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[],
        previous_findings=[PreviousFindingDTO(summary="импорты", status="fixed")],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert "Все замечания закрыты." in git_port.send_inline.await_args.kwargs["review"].general_comment


async def test_the_summary_never_claims_more_fixes_than_findings(service, ai_port, git_port):
    git_port.fetch_review_context.return_value = _context(FINDING)
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[],
        previous_findings=[PreviousFindingDTO(summary="a", status="fixed") for _ in range(5)],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert "исправлено: 1 из 1." in git_port.send_inline.await_args.kwargs["review"].general_comment


async def test_no_summary_without_earlier_findings(service, ai_port, git_port):
    git_port.fetch_review_context.return_value = _context(DISCUSSION)
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_inline.await_args.kwargs["review"].general_comment
    assert published == f"🤖 **ReVu**\ninline review\n\n{MARKER}"


async def test_no_summary_when_the_model_reported_nothing(service, ai_port, git_port, caplog):
    """A claim of zero fixes would be worse than no line at all."""
    git_port.fetch_review_context.return_value = _context(FINDING)
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    with caplog.at_level("WARNING"):
        await service.process_webhook(tenant=tenant, webhook_data=make_event())

    assert "📊" not in git_port.send_inline.await_args.kwargs["review"].general_comment
    assert "omitting the progress line" in caplog.text


async def test_comment_mode_publishes_the_model_text_as_is(service, ai_port, git_port):
    """In comment mode the prompt asks the model for the progress line itself."""
    git_port.fetch_review_context.return_value = _context(FINDING)
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.COMMENT)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_comment.await_args.kwargs["review"]
    assert published.startswith("🤖 **ReVu** · повторное ревью\n\n")
    assert published.endswith(f"comment review\n\n{MARKER}")


async def test_a_first_review_is_signed_and_headlined(service, ai_port, git_port):
    """The signature is what makes a later review recognise its own words."""
    git_port.fetch_review_context.return_value = None
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_inline.await_args.kwargs["review"]
    assert published.general_comment.startswith("🤖 **ReVu**\n")
    assert "повторное ревью" not in published.general_comment
    assert is_marked(published.general_comment) is True


async def test_every_inline_comment_is_badged_and_signed(service, ai_port, git_port):
    """Under one account the avatar says nothing, so the text has to."""
    from revu.domain.entities.dto.ai_provider_dto import GitHubReviewCommentDTO

    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="первое")],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    published = git_port.send_inline.await_args.kwargs["review"]
    assert published.comments[0].body.startswith("🤖 ReVu: первое")
    assert is_marked(published.comments[0].body) is True


async def test_a_signed_review_is_recognised_on_the_next_run(service, ai_port, git_port):
    """Round trip: what ReVu publishes is what a later review reads back as its own."""
    from revu.domain.entities.dto.ai_provider_dto import GitHubReviewCommentDTO

    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="первое")],
    )
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.INLINE)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())
    published = git_port.send_inline.await_args.kwargs["review"]

    # A host reports back what was posted.
    git_port.fetch_review_context.return_value = ReviewContextDTO(
        comments=(
            PreviousCommentDTO(
                author="ivan",
                body=published.comments[0].body,
                is_revu=is_marked(published.comments[0].body),
            ),
        )
    )
    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    context = ai_port.get_inline_response.await_args.args[0].previous_review
    assert context is not None
    assert context.findings[0].body.startswith("🤖 ReVu: первое")
    assert "повторное ревью" in git_port.send_inline.await_args.kwargs["review"].general_comment
