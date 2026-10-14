"""A review as data, for whatever consumes the pipeline's output.

The text publisher is for people reading a job log; this one is for the things that
read a job's output — a script, an artifact, the next step of a pipeline that wants
to decide something for itself.
"""

import json
import sys
from dataclasses import asdict, is_dataclass
from typing import TextIO

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO


class JsonPublisher:
    """Prints one JSON object per review."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream if stream is not None else sys.stdout

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        self._emit({"kind": "comment", "repo": repo_owner, "number": index, "body": review})

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        self._emit(
            {
                "kind": "inline",
                "repo": repo_owner,
                "number": index,
                "sha": sha,
                "summary": review.general_comment,
                "comments": [_comment(item) for item in review.comments],
            }
        )

    def _emit(self, payload: dict) -> None:
        print(json.dumps(payload, ensure_ascii=False), file=self._stream, flush=True)


def _comment(comment: object) -> dict:
    """Every field of a host's comment, or at least its text."""
    if is_dataclass(comment) and not isinstance(comment, type):
        return asdict(comment)

    return {"body": getattr(comment, "body", "")}
