from typing import cast
from urllib.parse import quote, urljoin

from revu.application.entities.config import GitConnectionConfig
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HttpGatewayError,
)
from revu.application.entities.exceptions.provider_exceptions import (
    GitProviderException,
)
from revu.application.entities.review_marker import clean, is_marked
from revu.domain.entities.dto.ai_provider_dto import (
    GitLabReviewCommentDTO,
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
from revu.infrastructure.git_providers.gitlab.helpers import json_diff_to_unified
from revu.infrastructure.git_providers.repository_files import (
    MAX_TREE_ENTRIES,
    decode,
)
from revu.infrastructure.git_providers.review_context import (
    CONTEXT_PAGE_SIZE,
    MAX_CONTEXT_PAGES,
    body_of,
    build_context,
    fetch_list_pages,
    sort_key,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

# GitLab caps per_page at 100 and reports no total, so paging stops on a short
# page. The limit only guards against a server that always answers a full one.
DIFF_PAGE_SIZE = 100
MAX_DIFF_PAGES = 100


class GitlabPort(GitProviderProtocol):
    """GitLab, including self-managed instances.

    Inline notes are positioned by three commit SHAs that only the versions
    endpoint reports, so publishing them costs one extra request per review.
    """

    DEFAULT_API_URL = "https://gitlab.com"

    def __init__(self, http_client: HttpClientGateway, config: GitConnectionConfig) -> None:
        self.http_client = http_client
        self.config = config
        self.gitlab_token = config.user_token
        self.gitlab_url = config.base_url or self.DEFAULT_API_URL

    def _get_headers(self) -> dict[str, str]:
        return {"PRIVATE-TOKEN": self.gitlab_token}

    def _api_url(self, path: str) -> str:
        return urljoin(self.gitlab_url.rstrip("/") + "/", f"api/v4/{path}")

    @staticmethod
    def _project(repo: str) -> str:
        """Encode a project path: GitLab accepts an id or ``group%2Fproject``."""
        return quote(repo, safe="")

    async def fetch_diff(self, repo: str, index: int) -> str:
        """Fetch every diff page and render it as one unified diff.

        GitLab paginates ``/diffs`` and returns a bare array, so the end of the
        data is a page shorter than the requested size (the gateway hands back the
        parsed body, not the ``X-Next-Page`` header).
        """
        project = self._project(repo)
        file_diffs: list[dict] = []

        for page in range(1, MAX_DIFF_PAGES + 1):
            page_diffs = await self.http_client.get(
                url=self._api_url(
                    f"projects/{project}/merge_requests/{index}/diffs?per_page={DIFF_PAGE_SIZE}&page={page}"
                ),
                headers=self._get_headers(),
            )

            if not isinstance(page_diffs, list) or not page_diffs:
                break

            file_diffs.extend(diff for diff in page_diffs if isinstance(diff, dict))

            if len(page_diffs) < DIFF_PAGE_SIZE:
                break

        return json_diff_to_unified(file_diffs)

    @staticmethod
    def _note(raw: dict) -> PreviousCommentDTO | None:
        if raw.get("system"):
            # "changed the description", "added 3 commits" and friends.
            return None

        raw_body = body_of(raw)
        if not raw_body:
            return None

        author = raw.get("author")
        author_name = author.get("username") if isinstance(author, dict) else ""
        raw_position = raw.get("position")
        position = raw_position if isinstance(raw_position, dict) else {}
        path = position.get("new_path") or position.get("old_path")
        line = position.get("new_line") or position.get("old_line")

        return PreviousCommentDTO(
            author=author_name if isinstance(author_name, str) else "",
            # The signature, not the author: ReVu often runs on the author's own
            # account, and then authorship says nothing.
            body=clean(raw_body),
            is_revu=is_marked(raw_body),
            path=path if isinstance(path, str) else None,
            line=line if isinstance(line, int) else None,
            resolved=bool(raw.get("resolved")),
        )

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        """Notes on the merge request, oldest first.

        GitLab keeps the whole conversation — including system notes — in one
        list, and reports whether a note was resolved.
        """
        project = self._project(repo)

        raws = await fetch_list_pages(
            self.http_client,
            lambda page: self._api_url(
                f"projects/{project}/merge_requests/{index}/notes"
                f"?per_page={CONTEXT_PAGE_SIZE}&page={page}&sort=asc&order_by=created_at"
            ),
            self._get_headers(),
        )

        return build_context((sort_key(raw), self._note(raw)) for raw in raws)

    async def fetch_file(self, repo: str, path: str, revision: str) -> str | None:
        """The file's text at a revision, or ``None`` when the path is not there."""
        project = self._project(repo)
        encoded = quote(path, safe="")

        try:
            content = await self.http_client.get(
                url=self._api_url(f"projects/{project}/repository/files/{encoded}/raw?ref={revision}"),
                headers=self._get_headers(),
                expect_json=False,
            )
        except HttpGatewayError as exc:
            if exc.status_code == 404:
                return None

            raise

        return decode(content)

    async def list_files(self, repo: str, revision: str) -> tuple[str, ...]:
        """Every file of the tree; GitLab pages the listing like the diff endpoint."""
        project = self._project(repo)
        paths: list[str] = []

        for page in range(1, MAX_CONTEXT_PAGES + 1):
            payload = await self.http_client.get(
                url=self._api_url(
                    f"projects/{project}/repository/tree"
                    f"?recursive=true&per_page={CONTEXT_PAGE_SIZE}&page={page}&ref={revision}"
                ),
                headers=self._get_headers(),
            )

            entries = [entry for entry in payload if isinstance(entry, dict)] if isinstance(payload, list) else []
            paths.extend(
                entry["path"] for entry in entries if entry.get("type") == "blob" and isinstance(entry.get("path"), str)
            )

            if len(entries) < CONTEXT_PAGE_SIZE or len(paths) >= MAX_TREE_ENTRIES:
                break

        return tuple(paths[:MAX_TREE_ENTRIES])

    async def send_comment(self, repo_owner: str, review: str, index: int) -> None:
        await self.http_client.post(
            url=self._api_url(f"projects/{self._project(repo_owner)}/merge_requests/{index}/notes"),
            headers=self._get_headers(),
            payload={"body": review},
        )

    async def _get_position_shas(self, project: str, index: int) -> tuple[str, str, str]:
        """The base, head and start SHAs a GitLab diff note is positioned against."""
        versions = await self.http_client.get(
            url=self._api_url(f"projects/{project}/merge_requests/{index}/versions"),
            headers=self._get_headers(),
        )

        latest = versions[0] if isinstance(versions, list) and versions else None
        if not isinstance(latest, dict):
            raise GitProviderException(f"GitLab reported no diff versions for merge request {index}")

        base_sha = latest.get("base_commit_sha")
        head_sha = latest.get("head_commit_sha")
        start_sha = latest.get("start_commit_sha")

        if not all(isinstance(sha, str) and sha for sha in (base_sha, head_sha, start_sha)):
            raise GitProviderException(f"GitLab reported incomplete diff versions for merge request {index}")

        # Verified just above; `all` does not narrow the three names for the checker.
        return cast(tuple[str, str, str], (base_sha, head_sha, start_sha))

    async def _send_discussion(
        self,
        project: str,
        index: int,
        comment: GitLabReviewCommentDTO,
        shas: tuple[str, str, str],
    ) -> None:
        base_sha, head_sha, start_sha = shas

        position: dict[str, object] = {
            "position_type": "text",
            "base_sha": base_sha,
            "head_sha": head_sha,
            "start_sha": start_sha,
            # GitLab requires both paths; a comment only ever names the file as it
            # exists after the change, which is also the common case for renames.
            "new_path": comment.path,
            "old_path": comment.path,
        }

        if comment.new_line is not None:
            position["new_line"] = comment.new_line

        if comment.old_line is not None:
            position["old_line"] = comment.old_line

        await self.http_client.post(
            url=self._api_url(f"projects/{project}/merge_requests/{index}/discussions"),
            headers=self._get_headers(),
            payload={"body": comment.body, "position": position},
        )

    async def send_inline(self, sha: str, repo_owner: str, review: ReviewResponseDTO, index: int) -> None:
        project = self._project(repo_owner)
        shas: tuple[str, str, str] | None = None

        for comment in review.comments:
            if not isinstance(comment, GitLabReviewCommentDTO):
                raise UnsupportedReviewCommentException(
                    f"{type(comment).__name__} comments cannot be published to GitLab"
                )

            if shas is None:
                # Fetched once per review, and only when there is something to post.
                shas = await self._get_position_shas(project, index)

            await self._send_discussion(project, index, comment, shas)

        await self.send_comment(repo_owner, review.general_comment, index)
