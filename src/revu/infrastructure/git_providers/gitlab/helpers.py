"""Turn GitLab's diff representation into a unified diff.

GitLab answers ``/merge_requests/:iid/diffs`` with one object per changed file
whose ``diff`` field holds only the hunks: the file headers that a unified diff
needs are not part of it, and a created or deleted file has no path on one side.
"""

DEV_NULL = "/dev/null"


def _path(value: object) -> str:
    return value if isinstance(value, str) else ""


def json_diff_to_unified(diffs: object) -> str:
    """Render the ``/diffs`` array as a unified diff.

    The payload comes from a remote server, so it is read defensively: a file
    whose diff is empty (binary, collapsed or above the diff limit) carries no
    lines to review and is skipped rather than rendered as an empty file.
    """
    lines: list[str] = []

    if not isinstance(diffs, list):
        return ""

    for file_diff in diffs:
        if not isinstance(file_diff, dict):
            continue

        text = file_diff.get("diff")
        if not isinstance(text, str) or not text.strip():
            continue

        old_path = _path(file_diff.get("old_path"))
        new_path = _path(file_diff.get("new_path"))

        source = DEV_NULL if file_diff.get("new_file") else f"a/{old_path}"
        destination = DEV_NULL if file_diff.get("deleted_file") else f"b/{new_path}"

        lines.append(f"diff --git a/{old_path or new_path} b/{new_path or old_path}")
        lines.append(f"--- {source}")
        lines.append(f"+++ {destination}")
        lines.append(text.rstrip("\n"))

    return "\n".join(lines)
