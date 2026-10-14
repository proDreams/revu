import pytest

from revu.infrastructure.git_providers.bitbucket.helpers import json_diff_to_unified

pytestmark = pytest.mark.unit


def _payload(**overrides) -> dict:
    diff = {
        "source": {"toString": "app.py"},
        "destination": {"toString": "app.py"},
        "hunks": [
            {
                "sourceLine": 1,
                "sourceSpan": 2,
                "destinationLine": 1,
                "destinationSpan": 2,
                "segments": [
                    {"type": "CONTEXT", "lines": [{"line": "context"}]},
                    {"type": "REMOVED", "lines": [{"line": "old"}]},
                    {"type": "ADDED", "lines": [{"line": "new"}]},
                ],
            }
        ],
    }
    diff.update(overrides)

    return {"diffs": [diff]}


def test_json_diff_to_unified_renders_headers_and_segments():
    result = json_diff_to_unified(_payload()).splitlines()

    assert result[0] == "diff --git a/app.py b/app.py"
    assert result[1] == "--- a/app.py"
    assert result[2] == "+++ b/app.py"
    assert result[3] == "@@ -1,2 +1,2 @@"
    assert result[4] == " context"
    assert result[5] == "-old"
    assert result[6] == "+new"


def test_json_diff_to_unified_handles_missing_source_and_destination():
    """A created or deleted file must render `/dev/null`, not `a//dev/null`."""
    payload = _payload(source=None, destination=None)

    result = json_diff_to_unified(payload).splitlines()

    assert result[0] == "diff --git /dev/null /dev/null"
    assert result[1] == "--- /dev/null"
    assert result[2] == "+++ /dev/null"


def test_json_diff_to_unified_prefixed_only_for_known_sides():
    assert json_diff_to_unified(_payload(source=None)).splitlines()[1] == "--- /dev/null"
    assert json_diff_to_unified(_payload(destination=None)).splitlines()[2] == "+++ /dev/null"


def test_json_diff_to_unified_handles_missing_line_text():
    payload = _payload(
        hunks=[
            {
                "sourceLine": 1,
                "sourceSpan": 1,
                "destinationLine": 1,
                "destinationSpan": 1,
                "segments": [{"type": "ADDED", "lines": [{}]}],
            }
        ]
    )

    result = json_diff_to_unified(payload).splitlines()

    assert result[4] == "+"


def test_json_diff_to_unified_skips_unknown_segment_types():
    payload = _payload(
        hunks=[
            {
                "sourceLine": 1,
                "sourceSpan": 1,
                "destinationLine": 1,
                "destinationSpan": 1,
                "segments": [
                    {"type": "SOMETHING_NEW", "lines": [{"line": "ignored"}]},
                    {"type": "ADDED", "lines": [{"line": "kept"}]},
                ],
            }
        ]
    )

    result = json_diff_to_unified(payload)

    assert "ignored" not in result
    assert "+kept" in result


def test_json_diff_to_unified_tolerates_missing_keys():
    """A truncated server response must not crash a review with a KeyError."""
    assert json_diff_to_unified({}) == ""
    assert json_diff_to_unified({"diffs": None}) == ""
    assert json_diff_to_unified({"diffs": ["not-a-dict"]}) == ""
    assert json_diff_to_unified({"diffs": [{"destination": {"toString": "a.py"}}]}) == (
        "diff --git /dev/null b/a.py\n--- /dev/null\n+++ b/a.py"
    )
    assert json_diff_to_unified({"diffs": [{"hunks": [{"segments": [{"type": "ADDED"}]}]}]}) != ""


def test_json_diff_to_unified_skips_malformed_hunks_and_segments():
    payload = _payload(
        hunks=[
            "not-a-hunk",
            {
                "sourceLine": 1,
                "sourceSpan": 1,
                "destinationLine": 1,
                "destinationSpan": 1,
                "segments": ["not-a-segment", {"type": "ADDED", "lines": [{"line": "kept"}]}],
            },
        ]
    )

    result = json_diff_to_unified(payload)

    assert "+kept" in result
    assert "not-a" not in result
