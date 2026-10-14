SEGMENT_PREFIXES = {"CONTEXT": " ", "ADDED": "+", "REMOVED": "-"}

DEV_NULL = "/dev/null"


def _file_path(ref: object) -> str:
    """Return the ``toString`` path of a Bitbucket file reference."""
    if isinstance(ref, dict):
        path = ref.get("toString")
        if isinstance(path, str) and path:
            return path

    return DEV_NULL


def _side_path(path: str, prefix: str) -> str:
    """Prefix a path with ``a``/``b``, keeping ``/dev/null`` unprefixed."""
    return DEV_NULL if path == DEV_NULL else f"{prefix}/{path}"


def json_diff_to_unified(diff_json: dict) -> str:
    """Render Bitbucket's JSON diff representation as a unified diff.

    The payload comes from a remote server, so every level is read defensively:
    Bitbucket omits ``source``/``destination`` for created and deleted files,
    and an unexpected segment type must not crash a review with a ``KeyError``.
    Unknown pieces are skipped rather than raising, because a partial diff still
    produces a useful review.
    """
    lines: list[str] = []

    for file_diff in diff_json.get("diffs") or []:
        if not isinstance(file_diff, dict):
            continue

        source = _side_path(_file_path(file_diff.get("source")), prefix="a")
        destination = _side_path(_file_path(file_diff.get("destination")), prefix="b")

        lines.append(f"diff --git {source} {destination}")
        lines.append(f"--- {source}")
        lines.append(f"+++ {destination}")

        for hunk in file_diff.get("hunks") or []:
            if not isinstance(hunk, dict):
                continue

            lines.append(
                f"@@ -{hunk.get('sourceLine', 0)},{hunk.get('sourceSpan', 0)} "
                f"+{hunk.get('destinationLine', 0)},{hunk.get('destinationSpan', 0)} @@"
            )

            for segment in hunk.get("segments") or []:
                if not isinstance(segment, dict):
                    continue

                prefix = SEGMENT_PREFIXES.get(str(segment.get("type", "")).upper())
                if prefix is None:
                    continue

                for line in segment.get("lines") or []:
                    text = line.get("line", "") if isinstance(line, dict) else ""
                    lines.append(f"{prefix}{text}")

    return "\n".join(lines)
