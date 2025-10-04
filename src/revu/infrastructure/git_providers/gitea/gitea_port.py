from dataclasses import asdict
from urllib.parse import urljoin

from revu.application.config import get_settings
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.http_client.http_client_gateway import (
    HttpClientGateway,
    get_http_gateway,
)


class GiteaPort(GitProviderProtocol):
    def __init__(self, http_client: HttpClientGateway) -> None:
        self.http_client = http_client
        self.git_conf = get_settings().GIT_PROVIDER_CONFIG
        self.gitea_token = self.git_conf.GIT_PROVIDER_USER_TOKEN
        self.gitea_url = self.git_conf.GIT_PROVIDER_URL

    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.gitea_token}"}

    async def fetch_diff(self, repo: str, index: int) -> str:
        fetch_path = f"api/v1/repos/{repo}/pulls/{index}.diff"
        diff_url = urljoin(self.gitea_url.rstrip("/") + "/", fetch_path)

        return await self.http_client.get(url=diff_url, headers=self._get_headers(), expect_json=False)

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        comment_path = f"api/v1/repos/{repo_owner}/issues/{index}/comments"
        comment_url = urljoin(self.gitea_url.rstrip("/") + "/", comment_path)

        data = {"body": review}

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        inline_path = f"api/v1/repos/{repo_owner}/pulls/{index}/reviews"
        comment_url = urljoin(self.gitea_url.rstrip("/") + "/", inline_path)

        data = {
            "commit_id": sha,
            "body": review.general_comment,
            "comments": [asdict(comment) for comment in review.comments],
        }

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)


def get_gitea_port() -> GiteaPort:
    return GiteaPort(http_client=get_http_gateway())
