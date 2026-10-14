"""A review as a GitLab Code Quality report.

GitLab shows these findings in the merge request widget, and that is the point: the
report is an artifact, not a comment, so it needs no permission to write anything.
It is the answer to GitLab's CI job token being able to read a merge request and
unable to leave a note in it.

The format is the Code Climate subset GitLab accepts, and the fields that matter are
the location (which file, which line) and a fingerprint that stays the same across
runs, so GitLab can tell a finding that is still there from a new one.
"""

import hashlib
import json
from pathlib import Path

from revu.application.config import get_logger
from revu.application.entities import review_marker
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.infrastructure.publishers.comment_fields import line_of, path_of

logger = get_logger(name=__name__)

#: What a review comment is worth, in the report's own vocabulary. The model is not
#: asked for a severity, so claiming more than "worth a look" would be an invention.
SEVERITY = "minor"

#: Name the widget groups findings under.
CHECK_NAME = "ReVu"


class GitLabCodeQualityPublisher:
    """Writes the report a merge request reads, and nothing else."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        """A paragraph has no line to point at, so there is no report to write.

        The report is still written — empty — because `artifacts:reports:codequality`
        pointing at a missing file fails the job.
        """
        self._write([])

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        entries = [entry for entry in (self._entry(comment) for comment in review.comments) if entry is not None]

        if len(entries) != len(review.comments):
            logger.info(
                "the code quality report holds %d of %d comments: the rest carry no line",
                len(entries),
                len(review.comments),
            )

        self._write(entries)

    @staticmethod
    def _entry(comment: object) -> dict | None:
        """One finding, or ``None`` when it cannot be placed on a line."""
        line = line_of(comment)
        path = path_of(comment)

        if line is None or path is None:
            return None

        # The widget renders a description as text, and ReVu identifies itself
        # through `check_name` here, so the signature would be noise.
        body = review_marker.clean(str(getattr(comment, "body", "")))

        return {
            "description": body,
            "check_name": CHECK_NAME,
            "severity": SEVERITY,
            # Stable for the same finding in the same place: a fingerprint that
            # changes every run would make every finding look brand new.
            "fingerprint": hashlib.sha1(f"{path}:{line}:{body}".encode()).hexdigest(),
            "location": {"path": path, "lines": {"begin": line}},
        }

    def _write(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("wrote the code quality report to %s (%d findings)", self._path, len(entries))
