"""Sending one review to several destinations.

A review has more than one reader: the author sees it in the pull request, whoever
debugs the pipeline sees it in the job log, and GitLab sees it in a report. Each of
those is a publisher; this one lets them all have it.
"""

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.comment_publisher_protocol import CommentPublisherProtocol


class CompositePublisher:
    """Publishes every review to each of its publishers, in the order given."""

    def __init__(self, *publishers: CommentPublisherProtocol) -> None:
        self._publishers = publishers

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        for publisher in self._publishers:
            await publisher.send_comment(repo_owner=repo_owner, review=review, index=index)

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        for publisher in self._publishers:
            await publisher.send_inline(sha=sha, repo_owner=repo_owner, review=review, index=index)


def combine_publishers(*publishers: CommentPublisherProtocol) -> CommentPublisherProtocol:
    """One publisher, whether the caller asked for one destination or several."""
    if len(publishers) == 1:
        return publishers[0]

    return CompositePublisher(*publishers)
