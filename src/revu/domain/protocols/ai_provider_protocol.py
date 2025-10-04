from typing import Protocol

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO


class AIProviderProtocol(Protocol):
    async def get_comment_response(self, diff: str) -> str:
        """

        :param diff:
        :return:
        """
        ...

    async def get_inline_response(self, diff: str, git_provider: str) -> ReviewResponseDTO:
        """

        :param diff:
        :param git_provider:
        :return:
        """

        ...
