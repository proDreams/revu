from typing import Protocol

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO


class AIProviderProtocol(Protocol):
    async def get_comment_response(self, diff: str, pr_title: str, pr_body: str | None = None) -> str:
        """

        :param diff:
        :param pr_title:
        :param pr_body:
        :return:
        """
        ...

    async def get_inline_response(
        self, diff: str, git_provider: str, pr_title: str, pr_body: str | None = None
    ) -> ReviewResponseDTO:
        """

        :param diff:
        :param git_provider:
        :param pr_title:
        :param pr_body:
        :return:
        """

        ...
