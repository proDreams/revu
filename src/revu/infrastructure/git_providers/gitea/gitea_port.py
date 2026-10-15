from dataclasses import asdict
from urllib.parse import urljoin

from revu.application.entities.config import GitConnectionConfig
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.github_compatible import (
    GithubCompatibleComments,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GiteaPort(GithubCompatibleComments, GitProviderProtocol):
    #: Gitea mirrors the GitHub API, one prefix deeper.
    API_PREFIX = "api/v1/"

    def __init__(self, http_client: HttpClientGateway, config: GitConnectionConfig) -> None:
        self.http_client = http_client
        self.config = config
        self.gitea_token = config.user_token
        self._login: str | None = None
        self.gitea_url = config.resolved_base_url

    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.gitea_token}"}

    def _url(self, path: str) -> str:
        return urljoin(self.gitea_url.rstrip("/") + "/", path)

    async def fetch_diff(self, repo: str, index: int) -> str:
        content = await self.http_client.get(
            url=self._url(f"api/v1/repos/{repo}/pulls/{index}.diff"),
            headers=self._get_headers(),
            expect_json=False,
        )

        return content.decode("utf-8", errors="replace") if isinstance(content, bytes) else content

    def _conversation_paths(self, repo: str, index: int) -> tuple[tuple[str, bool], ...]:
        """Gitea's own routes, which differ from GitHub's.

        Gitea serves the issue timeline — and an inline review comment is an issue
        comment there, carrying a `pull_request_url` — plus `/pulls/{index}/reviews`
        for the review bodies. GitHub's `/pulls/{index}/comments` does not exist in
        Gitea's API at all: calling it answers 404 and costs the whole history, so a
        repeated review would never see its own earlier inline findings.
        """
        return (
            (f"{self.API_PREFIX}repos/{repo}/issues/{index}/comments", False),
            (f"{self.API_PREFIX}repos/{repo}/pulls/{index}/reviews", False),
        )

    def _file_request(self, repo: str, path: str, revision: str) -> tuple[str, dict[str, str]]:
        return self._url(f"{self.API_PREFIX}repos/{repo}/raw/{path}?ref={revision}"), self._get_headers()

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        data = {"body": review}

        await self.http_client.post(
            url=self._url(f"api/v1/repos/{repo_owner}/issues/{index}/comments"),
            headers=self._get_headers(),
            payload=data,
        )

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        data = {
            "commit_id": sha,
            "body": review.general_comment,
            "comments": [asdict(comment) for comment in review.comments],
        }

        await self.http_client.post(
            url=self._url(f"api/v1/repos/{repo_owner}/pulls/{index}/reviews"),
            headers=self._get_headers(),
            payload=data,
        )
