import asyncio
from unittest.mock import AsyncMock

import pytest

from revu.application.entities.enums.webhook_service_enums import ReviewModeEnum
from revu.application.entities.exceptions.webhook_service_exceptions import (
    ReviewModeException,
)
from revu.application.entities.tenant import GitConnection, TenantContext
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
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
    return WebhookService()


def make_tenant(ai_port, git_port, **connection) -> TenantContext:
    return TenantContext(
        connection=GitConnection.build(config=make_connection(**connection), port=git_port),
        ai_port=ai_port,
    )


async def test_comment_mode_sends_one_comment(service, ai_port, git_port):
    tenant = make_tenant(ai_port, git_port, review_mode=ReviewModeEnum.COMMENT)

    await service.process_webhook(tenant=tenant, webhook_data=make_event())

    git_port.send_comment.assert_awaited_once_with(repo_owner="owner/repo", review="comment review", index=7)
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

    annotated = WebhookService.annotate_diff(diff_text=diff)

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

    annotated = WebhookService.annotate_diff(diff_text=diff)

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

    annotated = WebhookService.annotate_diff(diff_text=diff)

    assert "No newline at end of file" not in annotated
    assert "- [1] old" in annotated
    assert "+ [1] new" in annotated


def test_annotate_diff_passes_empty_text_through():
    assert WebhookService.annotate_diff(diff_text="") == ""
