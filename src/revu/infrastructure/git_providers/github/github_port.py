from dataclasses import asdict
from urllib.parse import urljoin

from revu.application.entities.config import GitConnectionConfig
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.github_compatible import (
    GithubCompatibleComments,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GithubPort(GithubCompatibleComments, GitProviderProtocol):
    DEFAULT_API_URL = "https://api.github.com"

    def __init__(self, http_client: HttpClientGateway, config: GitConnectionConfig) -> None:
        self.http_client = http_client
        self.config = config
        self.github_token = config.user_token
        self._login: str | None = None
        # GitHub Enterprise Server serves its REST API under `/api/v3`, so a
        # self-hosted instance has to be configured as
        # `https://ghe.example.com/api/v3`. When unset, github.com is used.
        self.github_url = config.base_url or self.DEFAULT_API_URL

    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.github_token}"}

    def _url(self, path: str) -> str:
        return urljoin(f"{self.github_url.rstrip('/')}/", path)

    async def fetch_diff(self, repo: str, index: int) -> str:
        headers = self._get_headers()
        headers["Accept"] = "application/vnd.github.v3.diff"

        content = await self.http_client.get(
            url=self._url(f"repos/{repo}/pulls/{index}.diff"),
            headers=headers,
            expect_json=False,
        )

        return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content

    def _file_request(self, repo: str, path: str, revision: str) -> tuple[str, dict[str, str]]:
        headers = self._get_headers()
        headers["Accept"] = "application/vnd.github.raw"

        return self._url(f"repos/{repo}/contents/{path}?ref={revision}"), headers

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        data = {"body": review}

        await self.http_client.post(
            url=self._url(f"repos/{repo_owner}/issues/{index}/comments"),
            headers=self._get_headers(),
            payload=data,
        )

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        # GitHub anchors inline comments by file line number and side, which is
        # what GitHubReviewCommentDTO carries; `position` is deprecated there.
        data = {
            "commit_id": sha,
            "body": review.general_comment,
            "comments": [asdict(comment) for comment in review.comments],
        }

        await self.http_client.post(
            url=self._url(f"repos/{repo_owner}/pulls/{index}/reviews"),
            headers=self._get_headers(),
            payload=data,
        )
