from unittest.mock import AsyncMock

import pytest

from revu.application.entities.exceptions.webhook_service_exceptions import (
    ReviewModeException,
)
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum

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
def service(ai_port, git_port):
    return WebhookService(ai_port=ai_port, git_port=git_port)


async def test_comment_mode_sends_plain_comment(service, ai_port, git_port, settings):
    settings["REVIEW_MODE"] = "comment"

    await service.process_webhook(webhook_data=make_event())

    git_port.send_comment.assert_awaited_once_with(repo_owner="owner/repo", review="comment review", index=7)
    git_port.send_inline.assert_not_awaited()
    # Comment mode passes the raw diff through untouched.
    ai_port.get_comment_response.assert_awaited_once_with(diff=DIFF, pr_title="Add feature", pr_body="Implements it")


async def test_inline_mode_sends_annotated_diff(service, ai_port, git_port, settings):
    settings["REVIEW_MODE"] = "inline"

    await service.process_webhook(webhook_data=make_event())

    git_port.send_inline.assert_awaited_once()
    git_port.send_comment.assert_not_awaited()

    annotated_diff = ai_port.get_inline_response.await_args.kwargs["diff"]
    assert "+ [2] new line" in annotated_diff
    assert "- [2] old line" in annotated_diff
    assert "  [1->1] context" in annotated_diff

    assert ai_port.get_inline_response.await_args.kwargs["git_provider"] == "gitea"


async def test_process_webhook_decodes_bytes_diff(service, ai_port, git_port, settings):
    settings["REVIEW_MODE"] = "comment"
    git_port.fetch_diff.return_value = DIFF.encode()

    await service.process_webhook(webhook_data=make_event())

    ai_port.get_comment_response.assert_awaited_once_with(diff=DIFF, pr_title="Add feature", pr_body="Implements it")


async def test_process_webhook_rejects_unknown_review_mode(service, settings):
    settings["REVIEW_MODE"] = "bogus"

    with pytest.raises(ReviewModeException) as exc_info:
        await service.process_webhook(webhook_data=make_event())

    assert "Unknown review mode" in str(exc_info.value)


async def test_annotate_diff_marks_added_file():
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


async def test_annotate_diff_marks_removed_file():
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


async def test_annotate_diff_drops_no_newline_marker():
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


async def test_annotate_diff_passes_empty_text_through():
    assert WebhookService.annotate_diff(diff_text="") == ""
