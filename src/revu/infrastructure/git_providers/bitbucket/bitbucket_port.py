from dataclasses import asdict
from urllib.parse import urljoin

from revu.application.config import get_settings
from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO, BitBucketReviewCommentDTO
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.http_client.http_client_gateway import (
    HttpClientGateway,
    get_http_gateway,
)
from .helpers import json_diff_to_unified


class BitbucketPort(GitProviderProtocol):
    def __init__(self, http_client: HttpClientGateway) -> None:
        self.http_client = http_client
        self.git_conf = get_settings().GIT_PROVIDER_CONFIG
        self.bitbucket_token = self.git_conf.GIT_PROVIDER_USER_TOKEN
        self.bitbucket_url = self.git_conf.GIT_PROVIDER_URL
        
    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bitbucket_token}"}
    
    async def fetch_diff(self, repo: str, index: int) -> str:
        fetch_path = f"rest/api/1.0/projects/{repo}/pull-requests/{index}/diff"
        diff_url = urljoin(self.bitbucket_url.rstrip("/") + "/", fetch_path)

        diff = await self.http_client.get(url=diff_url, headers=self._get_headers())

        return json_diff_to_unified(diff)
    
    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        comment_url = f"rest/api/1.0/projects/{repo_owner}/pull-requests/{index}/comments"
        comment_url = urljoin(self.bitbucket_url.rstrip("/") + "/", comment_url)
        data = {
            "text": review
        }

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)
    
    
    async def _send_inline(self, repo: str, text: str, index: int, path: str, lineType: str) -> None:
        comment_url = f"rest/api/1.0/projects/{repo}/pull-requests/{index}/comments"
        comment_url = urljoin(self.bitbucket_url.rstrip("/") + "/", comment_url)
        data = {
            "text": text,
            "anchor": {
                "path": path,
                "lineType": lineType,
                "line": index,
                "diffType": "EFFECTIVE"
            }
        }

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)
    
    
    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        comment_url = f"rest/api/1.0/projects/{repo_owner}/pull-requests/{index}/comments"
        comment_url = urljoin(self.bitbucket_url.rstrip("/") + "/", comment_url)
        
        await self.send_comment(repo_owner, review.general_comment, index)
        
        for comment in review.comments:
            if 'lineType' not in comment.__dict__:
                raise Exception('Only Bitbucket comments are supported')
            await self._send_inline(repo_owner, comment.body, index, comment.path, comment.lineType)


def get_bitbucket_port() -> BitbucketPort:
    return BitbucketPort(http_client=get_http_gateway())
