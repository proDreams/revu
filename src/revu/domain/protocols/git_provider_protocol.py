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

    async def fetch_file(self, repo: str, path: str, revision: str) -> str | None:
        """The text of one file at a revision, or ``None`` when it is not there.

        A missing path is a normal answer: callers probe for files a project may or
        may not have. Any other host failure is raised, so it stays visible.

        :param repo: repository the file belongs to
        :param path: repository-relative path
        :param revision: commit the file is read at
        """
        ...

    async def list_files(self, repo: str, revision: str) -> tuple[str, ...]:
        """Every file path of a repository at a revision.

        One request instead of a guess per candidate path, which is what makes
        "which test belongs to this file" answerable at all.

        :param repo: repository to list
        :param revision: commit the listing is taken at
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
