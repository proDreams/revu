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
    payload = _payload(source=None, destination=None)

    result = json_diff_to_unified(payload).splitlines()

    assert result[0] == "diff --git a//dev/null b//dev/null"


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
