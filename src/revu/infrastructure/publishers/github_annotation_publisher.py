"""A review as GitHub annotations.

``::warning file=…,line=…::text`` is a workflow command: the runner prints it and
GitHub turns it into an annotation next to the changed line. Nothing is requested
from the API and no token is spent, which is why this works in the places a comment
would not — and why it is worth having even when commenting is possible.
"""

import sys
from typing import TextIO

from revu.application.entities import review_marker
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.publishers.comment_fields import line_of, path_of

#: What the annotation is called in the interface. GitHub groups by this.
TITLE = "ReVu"

LEVEL = "warning"


def escape_data(text: str) -> str:
    """Escape a workflow command's message.

    GitHub reads its own commands out of the process output, so a newline in a
    review comment would end the command and turn the rest of the comment into
    plain log lines.
    """
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(value: str) -> str:
    """Escape a property, which has two more characters of its own."""
    return escape_data(value).replace(":", "%3A").replace(",", "%2C")


class GitHubAnnotationPublisher:
    """Prints the review as annotations the runner understands."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        """A general comment has no line, so there is nothing to annotate."""

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        for comment in review.comments:
            self._annotate(comment)

    def _annotate(self, comment: object) -> None:
        path = path_of(comment)

        if path is None:
            return

        properties = [f"file={escape_property(path)}"]

        line = line_of(comment)
        if line is not None:
            # endLine keeps the annotation on one line rather than a range.
            properties.extend([f"line={line}", f"endLine={line}"])

        properties.append(f"title={escape_property(TITLE)}")
        # An annotation is read as plain text in the interface, not as markdown, so
        # ReVu's signature would be visible noise there — and nothing reads an
        # annotation back, so there is nothing for the marker to identify.
        message = escape_data(review_marker.clean(str(getattr(comment, "body", ""))))

        print(f"::{LEVEL} {','.join(properties)}::{message}", file=self._stream, flush=True)
