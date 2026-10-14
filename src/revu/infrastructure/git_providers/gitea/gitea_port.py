from dataclasses import asdict
from urllib.parse import urljoin

from revu.application.config import get_settings
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GiteaPort(GitProviderProtocol):
    def __init__(self, http_client: HttpClientGateway) -> None:
        self.http_client = http_client
        self.git_conf = get_settings().GIT_PROVIDER_CONFIG
        self.gitea_token = self.git_conf.GIT_PROVIDER_USER_TOKEN
        self.gitea_url = self.git_conf.GIT_PROVIDER_URL

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
