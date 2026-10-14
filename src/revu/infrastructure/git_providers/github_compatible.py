"""Comment reading shared by the GitHub-compatible hosts.

GitHub and Gitea expose the same comment API; they differ only in their token
header, base URL and path prefix, which the concrete port supplies. Keeping one
implementation is what stops the two hosts from drifting apart.
"""

from functools import partial

from revu.application.entities.config import GitConnectionConfig
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HttpGatewayError,
)
from revu.application.entities.review_marker import clean, is_marked
from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.infrastructure.git_providers.repository_files import (
    MAX_TREE_ENTRIES,
    decode,
)
from revu.infrastructure.git_providers.review_context import (
    CONTEXT_PAGE_SIZE,
    body_of,
    build_context,
    fetch_list_pages,
    sort_key,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


class GithubCompatibleComments:
    """Mixin: reads a pull request's comments the way GitHub and Gitea do."""

    #: GitHub serves the API at the root, Gitea one prefix deeper.
    API_PREFIX = ""

    http_client: HttpClientGateway
    config: GitConnectionConfig

    # Abstract hooks: every concrete port supplies both, so these bodies are
    # unreachable by design.
    def _get_headers(self) -> dict[str, str]:  # pragma: no cover
        raise NotImplementedError

    def _url(self, path: str) -> str:  # pragma: no cover
        raise NotImplementedError

    def _comment_page_url(self, path: str, page: int) -> str:
        return self._url(f"{path}?per_page={CONTEXT_PAGE_SIZE}&page={page}")

    @staticmethod
    def _comment(raw: dict, *, inline: bool) -> PreviousCommentDTO | None:
        raw_body = body_of(raw)
        if not raw_body:
            # An approval, a label change or an empty review carries no text.
            return None

        author = raw.get("user")
        author_login = author.get("login") if isinstance(author, dict) else ""
        line = raw.get("line") if inline else None
        if inline and line is None:
            # The hosts keep the original anchor when the line moved.
            line = raw.get("original_line")

        return PreviousCommentDTO(
            author=author_login if isinstance(author_login, str) else "",
            # The signature, not the author: ReVu often runs on the author's own
            # account, and then authorship says nothing.
            body=clean(raw_body),
            is_revu=is_marked(raw_body),
            path=raw.get("path") if inline and isinstance(raw.get("path"), str) else None,
            line=line if isinstance(line, int) else None,
            # Neither host exposes review-thread resolution over REST.
            resolved=False,
        )

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        """Comments the pull request already has, oldest first.

        A pull request carries three separate conversations: the issue timeline,
        the inline review comments and the review bodies (where an inline summary
        goes). All three are read, or a re-review would miss its own summary.
        """
        headers = self._get_headers()

        mapped: list[tuple[str, PreviousCommentDTO | None]] = []

        for path, inline in (
            (f"{self.API_PREFIX}repos/{repo}/issues/{index}/comments", False),
            (f"{self.API_PREFIX}repos/{repo}/pulls/{index}/comments", True),
            (f"{self.API_PREFIX}repos/{repo}/pulls/{index}/reviews", False),
        ):
            raws = await fetch_list_pages(
                self.http_client,
                partial(self._comment_page_url, path),
                headers,
            )
            mapped.extend((sort_key(raw), self._comment(raw, inline=inline)) for raw in raws)

        return build_context(mapped)

    def _file_request(self, repo: str, path: str, revision: str) -> tuple[str, dict[str, str]]:
        """URL and headers that return a file's raw text. Host-specific."""
        raise NotImplementedError  # pragma: no cover - every concrete port supplies it

    async def fetch_file(self, repo: str, path: str, revision: str) -> str | None:
        """The file's text at a revision, or ``None`` when the path is not there."""
        url, headers = self._file_request(repo, path, revision)

        try:
            content = await self.http_client.get(url=url, headers=headers, expect_json=False)
        except HttpGatewayError as exc:
            # A path that does not exist is an answer, not a failure: callers probe.
            if exc.status_code == 404:
                return None

            raise

        return decode(content)

    async def list_files(self, repo: str, revision: str) -> tuple[str, ...]:
        """Every blob of the tree in one request; the hosts truncate it themselves."""
        payload = await self.http_client.get(
            url=self._url(f"{self.API_PREFIX}repos/{repo}/git/trees/{revision}?recursive=1"),
            headers=self._get_headers(),
        )

        entries = payload.get("tree") if isinstance(payload, dict) else None

        if not isinstance(entries, list):
            return ()

        paths = [
            entry["path"]
            for entry in entries
            if isinstance(entry, dict) and entry.get("type") == "blob" and isinstance(entry.get("path"), str)
        ]

        return tuple(paths[:MAX_TREE_ENTRIES])
