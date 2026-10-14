from urllib.parse import urljoin

from revu.application.entities.config import GitConnectionConfig
from revu.domain.entities.dto.ai_provider_dto import (
    BitBucketReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.bitbucket.helpers import json_diff_to_unified
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class BitbucketPort(GitProviderProtocol):
    def __init__(self, http_client: HttpClientGateway, config: GitConnectionConfig) -> None:
        self.http_client = http_client
        self.config = config
        self.bitbucket_token = config.user_token
        self.bitbucket_url = config.resolved_base_url

    def _get_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.bitbucket_token}"}

    def _url(self, path: str) -> str:
        return urljoin(self.bitbucket_url.rstrip("/") + "/", path)

    async def fetch_diff(self, repo: str, index: int) -> str:
        """Fetch every diff page and render it as one unified diff.

        Bitbucket paginates the ``diffs`` array. Only the first page used to be
        converted, so large pull requests were reviewed from a truncated diff.
        """
        diff_path = f"rest/api/1.0/projects/{repo}/pull-requests/{index}/diff"

        file_diffs: list[dict] = []
        start = 0

        while True:
            url = self._url(diff_path)
            if start:
                url = f"{url}?start={start}"

            page = await self.http_client.get(url=url, headers=self._get_headers())

            if not isinstance(page, dict):
                break

            file_diffs.extend(page.get("diffs") or [])

            next_page_start = page.get("nextPageStart")

            if page.get("isLastPage", True) or not isinstance(next_page_start, int) or next_page_start <= start:
                # The last condition also stops a misbehaving server from
                # making this loop forever.
                break

            start = next_page_start

        return json_diff_to_unified({"diffs": file_diffs})

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        comment_url = self._url(f"rest/api/1.0/projects/{repo_owner}/pull-requests/{index}/comments")
        data = {"text": review}

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)

    async def _send_inline(self, repo: str, text: str, index: int, path: str, line_type: str, line: int) -> None:
        comment_url = self._url(f"rest/api/1.0/projects/{repo}/pull-requests/{index}/comments")
        data = {"text": text, "anchor": {"path": path, "lineType": line_type, "line": line, "diffType": "EFFECTIVE"}}

        await self.http_client.post(url=comment_url, headers=self._get_headers(), payload=data)

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        for comment in review.comments:
            if not isinstance(comment, BitBucketReviewCommentDTO):
                raise UnsupportedReviewCommentException(
                    f"{type(comment).__name__} comments cannot be published to Bitbucket"
                )

            await self._send_inline(
                repo_owner,
                comment.body,
                index,
                comment.path,
                comment.lineType,
                comment.line,
            )

        await self.send_comment(repo_owner, review.general_comment, index)
