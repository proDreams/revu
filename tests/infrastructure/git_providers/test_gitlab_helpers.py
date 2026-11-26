"""The GitLab diff payload carries only hunks; a unified diff needs more."""

import pytest
from unidiff import PatchSet

from revu.infrastructure.git_providers.gitlab.helpers import json_diff_to_unified

pytestmark = pytest.mark.unit

HUNKS = "@@ -1,2 +1,2 @@\n context\n-old\n+new"


def test_a_changed_file_is_rendered_with_both_paths():
    unified = json_diff_to_unified(
        [{"old_path": "app.py", "new_path": "app.py", "diff": HUNKS}],
    )

    assert unified == (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n context\n-old\n+new"
    )


def test_a_new_file_has_no_source_path():
    unified = json_diff_to_unified(
        [{"old_path": "new.py", "new_path": "new.py", "diff": HUNKS, "new_file": True}],
    )

    assert "new file mode 100644" in unified
    assert "--- /dev/null" in unified
    assert "+++ b/new.py" in unified


def test_a_deleted_file_has_no_target_path():
    unified = json_diff_to_unified(
        [{"old_path": "gone.py", "new_path": "gone.py", "diff": HUNKS, "deleted_file": True}],
    )

    assert "deleted file mode 100644" in unified
    assert "--- a/gone.py" in unified
    assert "+++ /dev/null" in unified


@pytest.mark.parametrize("kind", ["new_file", "deleted_file"])
def test_a_created_or_deleted_file_is_a_parseable_unified_diff(kind):
    """Without the mode line unidiff rejects ``+++ /dev/null`` as target-less."""
    unified = json_diff_to_unified(
        [{"old_path": "image.png", "new_path": "image.png", "diff": HUNKS, kind: True}],
    )

    patched = PatchSet(unified)[0]

    assert patched.path == "image.png"
    assert (patched.is_added_file if kind == "new_file" else patched.is_removed_file) is True


def test_a_renamed_file_keeps_both_paths():
    unified = json_diff_to_unified(
        [{"old_path": "old.py", "new_path": "new.py", "diff": HUNKS, "renamed_file": True}],
    )

    assert unified.startswith("diff --git a/old.py b/new.py\n--- a/old.py\n+++ b/new.py\n")


@pytest.mark.parametrize(
    "file_diff",
    [
        {"old_path": "a.py", "new_path": "a.py", "diff": ""},  # binary
        {"old_path": "b.py", "new_path": "b.py", "diff": "   \n"},  # collapsed
        {"old_path": "c.py", "new_path": "c.py"},  # too large: no diff at all
        {"old_path": "d.py", "new_path": "d.py", "diff": None},
    ],
)
def test_a_file_without_content_is_skipped(file_diff):
    assert json_diff_to_unified([file_diff]) == ""


def test_the_diff_is_decoded_even_for_a_payload_that_is_not_a_list():
    assert json_diff_to_unified({"diffs": []}) == ""
    assert json_diff_to_unified(None) == ""


def test_entries_that_are_not_objects_are_skipped():
    assert json_diff_to_unified(["nonsense", {"diff": HUNKS}]) == (
        "diff --git a/ b/\n--- a/\n+++ b/\n@@ -1,2 +1,2 @@\n context\n-old\n+new"
    )


def test_pages_are_joined_into_one_diff():
    unified = json_diff_to_unified(
        [
            {"old_path": "a.py", "new_path": "a.py", "diff": HUNKS},
            {"old_path": "b.py", "new_path": "b.py", "diff": HUNKS},
        ]
    )

    assert unified.count("diff --git") == 2
