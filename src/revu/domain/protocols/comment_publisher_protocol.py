"""Putting a finished review where its readers will see it.

A separate protocol from reading (:mod:`git_reader_protocol`) because a review can
be produced without any way to write back: in a CI job the log is often the only
destination, and a pull request from a fork has no token to comment with. The
runner takes a publisher, so that case needs no special path.
"""

from typing import Protocol

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO


class CommentPublisherProtocol(Protocol):
    """Where a review goes once it exists."""

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        """Publish one comment under a pull request.

        :param repo_owner: repository the pull request belongs to
        :param review: the comment body
        :param index: pull request number
        """
        ...

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        """Publish a review with inline comments attached to lines of the diff.

        :param sha: the commit the comments are anchored to
        :param repo_owner: repository the pull request belongs to
        :param review: the review, its comments already signed and anchored
        :param index: pull request number
        """
        ...
