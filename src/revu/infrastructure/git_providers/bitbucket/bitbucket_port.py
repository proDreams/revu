from urllib.parse import urljoin

from revu.application.entities.config import GitConnectionConfig
from revu.application.entities.review_marker import clean, is_marked
from revu.domain.entities.dto.ai_provider_dto import (
    BitbucketReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)
from revu.domain.protocols.git_provider_protocol import GitProviderProtocol
from revu.infrastructure.git_providers.bitbucket.helpers import json_diff_to_unified
from revu.infrastructure.git_providers.review_context import (
    CONTEXT_PAGE_SIZE,
    MAX_CONTEXT_PAGES,
    build_context,
    sort_key,
)
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

    MAX_REPLY_DEPTH = 5

    def _flatten(self, raw: dict, depth: int = 0) -> list[dict]:
        """A Bitbucket thread keeps its replies nested; the prompt wants them flat."""
        flattened = [raw]

        if depth < self.MAX_REPLY_DEPTH:
            for reply in raw.get("comments") or []:
                if isinstance(reply, dict):
                    flattened.extend(self._flatten(reply, depth + 1))

        return flattened

    @staticmethod
    def _author_of(raw: dict) -> str:
        author = raw.get("author")
        if not isinstance(author, dict):
            return ""

        for field in ("name", "slug", "displayName"):
            value = author.get(field)
            if isinstance(value, str) and value:
                return value

        return ""

    @classmethod
    def _comment(cls, raw: dict) -> PreviousCommentDTO | None:
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            return None

        raw_anchor = raw.get("anchor")
        anchor = raw_anchor if isinstance(raw_anchor, dict) else {}
        raw_path = anchor.get("path")
        path_text = raw_path.get("toString") if isinstance(raw_path, dict) else None
        line = anchor.get("line")

        return PreviousCommentDTO(
            author=cls._author_of(raw),
            # The signature, not the author: ReVu often runs on the author's own
            # account, and then authorship says nothing.
            body=clean(text),
            is_revu=is_marked(text),
            path=path_text if isinstance(path_text, str) else None,
            line=line if isinstance(line, int) else None,
            # A Bitbucket comment is a task only when it is a blocker; both flags
            # say the thread is settled.
            resolved=raw.get("state") == "RESOLVED" or bool(raw.get("threadResolved")),
        )

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        """Pull request comments, oldest first, replies included."""
        base = f"rest/api/1.0/projects/{repo}/pull-requests/{index}/comments"
        mapped: list[tuple[str, PreviousCommentDTO | None]] = []
        start = 0

        for _ in range(MAX_CONTEXT_PAGES):
            url = self._url(f"{base}?limit={CONTEXT_PAGE_SIZE}")
            if start:
                url = f"{url}&start={start}"

            page = await self.http_client.get(url=url, headers=self._get_headers())

            if not isinstance(page, dict):
                break

            for raw in page.get("values") or []:
                if not isinstance(raw, dict):
                    continue

                for comment in self._flatten(raw):
                    mapped.append((sort_key(comment), self._comment(comment)))

            next_page_start = page.get("nextPageStart")

            if page.get("isLastPage", True) or not isinstance(next_page_start, int) or next_page_start <= start:
                break

            start = next_page_start

        return build_context(mapped)

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
            if not isinstance(comment, BitbucketReviewCommentDTO):
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
