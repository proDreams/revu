from typing import Protocol

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.review_context_dto import ReviewContextDTO


class GitProviderProtocol(Protocol):
    async def fetch_diff(self, repo: str, index: int) -> str:
        """

        :param repo:
        :param index:
        :return:
        """

        ...

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        """The comments the pull request already carries, oldest first.

        Returns ``None`` when there are none, which is what tells the review that
        it is the first look at this pull request rather than a follow-up.

        :param repo: repository the pull request belongs to
        :param index: pull request number
        """
        ...

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        """

        :param repo_owner:
        :param review:
        :param index:
        :return:
        """
        ...

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int):
        """

        :param sha:
        :param repo_owner:
        :param review:
        :param index:
        :return:
        """
        ...
