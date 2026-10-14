"""Reading a comment's place out of whichever host's shape it carries.

Every host addresses an inline comment differently: GitHub by line and side, GitLab
by the line on each side of the diff, Bitbucket by line and type, Gitea by a position
inside the diff. A destination that only *shows* a review — a log, a report, an
annotation — needs nothing but the file and the line, and this is where those are
worked out once instead of in each of them.
"""

#: Fields a line may hide in, best first: a new line is what a reader looks at.
LINE_FIELDS = ("line", "new_line", "old_line")


def line_of(comment: object) -> int | None:
    """The line a comment sits on, or ``None`` when its host did not say.

    Gitea speaks in diff positions rather than line numbers, and a comment that has
    just been written has no line at all; both answer ``None`` here.
    """
    for field in LINE_FIELDS:
        value = getattr(comment, field, None)

        if isinstance(value, int) and value > 0:
            return value

    return None


def path_of(comment: object) -> str | None:
    """The file a comment is about, or ``None`` when it does not say."""
    path = getattr(comment, "path", None)

    return path if isinstance(path, str) and path else None
