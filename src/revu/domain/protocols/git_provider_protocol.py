from typing import Protocol

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO


class GitProviderProtocol(Protocol):
    async def fetch_diff(self, repo: str, index: int) -> str:
        """

        :param repo:
        :param index:
        :return:
        """

        ...

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        pass

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int):
        pass
