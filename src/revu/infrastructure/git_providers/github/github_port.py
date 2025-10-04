from dataclasses import asdict

from revu.application.config import get_settings
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.http_client.http_client_gateway import (
    HttpClientGateway,
    get_http_gateway,
)


class GithubPort(GitProviderProtocol):
    def __init__(self, http_client: HttpClientGateway) -> None:
        self.http_client = http_client
        self.git_conf = get_settings().GIT_PROVIDER_CONFIG
        self.github_token = self.git_conf.GIT_PROVIDER_USER_TOKEN

    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"token {self.github_token}"}

    async def fetch_diff(self, repo: str, index: int) -> str:
        diff_url = f"https://api.github.com/repos/{repo}/pulls/{index}.diff"

        return await self.http_client.get(url=diff_url, headers=self._get_headers(), expect_json=False)

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        comment_url = f"https://api.github.com/repos/{repo_owner}/issues/{index}/comments"

        data = {"body": review}

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        inline_url = f"https://api.github.com/repos/{repo_owner}/pulls/{index}/reviews"

        data = {
            "commit_id": sha,
            "body": review.general_comment,
            "comments": [asdict(comment) for comment in review.comments],
        }

        await self.http_client.post(url=inline_url, headers=self._get_headers(), payload=data)


def get_github_port() -> GithubPort:
    return GithubPort(http_client=get_http_gateway())
