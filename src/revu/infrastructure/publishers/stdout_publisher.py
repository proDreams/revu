"""Publishing a review into the job log.

The fallback destination, and in CI often the right one: the log is attached to the
pipeline the change came from, needs no token, and cannot be left unread in a pull
request nobody watched. The markdown is printed as it would have been posted.
"""

import sys
from typing import TextIO

from revu.application.entities import review_marker
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.publishers.comment_fields import line_of, path_of


class StdoutPublisher:
    """Writes the review where the pipeline will capture it."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        self._write(review)

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        """The summary, then every inline comment as ``file:line``.

        Inline comments are addressed differently by every host (a line, two lines,
        a position in the diff), so the line is taken when one of them has it and
        omitted when none does — the text is what a reader of the log needs.
        """
        self._write(review.general_comment)

        if not review.comments:
            return

        self._write("\n**Замечания по строкам:**")

        for comment in review.comments:
            # The signature is invisible where the comment is posted and noise
            # here, so the list shows the finding itself.
            body = review_marker.clean(str(getattr(comment, "body", "")))
            self._write(f"- `{_where(comment)}` — {_one_line(body)}")

    def _write(self, text: str) -> None:
        print(text, file=self._stream, flush=True)


def _where(comment: object) -> str:
    """``path`` or ``path:line``, whichever the comment's host can say."""
    path = path_of(comment) or "?"
    line = line_of(comment)

    return f"{path}:{line}" if line is not None else path


def _one_line(body: object) -> str:
    """A comment body flattened, so one finding stays one log line."""
    text = body if isinstance(body, str) else ""

    return " ".join(text.split())
