"""How ReVu recognises the comments it published itself.

Authorship cannot answer that question: ReVu usually runs on the repository
owner's token, so the bot and the person are the same account, and every comment
they wrote would look like an earlier review — which then suppresses real findings
and reports nonsense progress.

ReVu therefore signs what it publishes. The signature is a trailing HTML comment:
invisible in a rendered pull request on GitHub, Gitea, GitLab and Bitbucket Data
Center (all CommonMark), and read back verbatim from every host's API.

The badge next to it is for people: under one account the author avatar says
nothing about who wrote a comment, so the text has to.
"""

MARKER = "<!-- revu -->"
BADGE = "🤖 **ReVu**"
RE_REVIEW_NOTE = " · повторное ревью"
INLINE_BADGE = "🤖 ReVu:"


def mark(body: str) -> str:
    """Sign a comment body so a later review recognises it.

    A body that already carries the signature is not signed twice, so re-publishing
    a comment cannot pile up markers.
    """
    text = body.rstrip()

    while text.endswith(MARKER):
        text = text[: -len(MARKER)].rstrip()

    return f"{text}\n\n{MARKER}" if text else MARKER


def is_marked(body: str) -> bool:
    """Whether ReVu published this comment.

    The marker has to be the last thing in the body: a reply that quotes an earlier
    comment must not be mistaken for one of ours.
    """
    return body.rstrip().endswith(MARKER)


def clean(body: str) -> str:
    """The comment as it was written, without the signature and the badges."""
    text = body.rstrip()

    if text.endswith(MARKER):
        text = text[: -len(MARKER)].rstrip()

    # An inline comment carries its badge at the start of the text itself, while the
    # summary header and the progress line are lines of their own.
    if text.startswith(INLINE_BADGE):
        text = text[len(INLINE_BADGE) :].strip()

    lines = text.splitlines()
    while lines and _is_decoration(lines[0]):
        lines.pop(0)

    return "\n".join(lines).strip()


def _is_decoration(line: str) -> bool:
    stripped = line.strip()

    return not stripped or stripped.startswith((BADGE, "📊"))


def header(*, re_review: bool) -> str:
    """The visible first line of a review, so authorship is clear to a reader."""
    return BADGE + (RE_REVIEW_NOTE if re_review else "")


def sign_inline(body: str) -> str:
    """Badge and sign one inline comment."""
    return mark(f"{INLINE_BADGE} {body.strip()}")
