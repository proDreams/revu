"""Reading a change from the checkout a pipeline has already made.

In CI there is no reason to ask a host for anything: the repository is on disk, the
diff is one git command away, and every file a review wants is already there. That
also makes deep context free — no requests, no rate limits, and no token scope
needed to read a tree.

What a checkout cannot provide is the conversation: pull request comments live in
the host, not in git. So this reader takes an optional host reader and delegates
that one question to it.
"""

import asyncio
from pathlib import Path

from revu.application.config import get_logger
from revu.domain.entities.dto.review_context_dto import ReviewContextDTO
from revu.domain.protocols.git_reader_protocol import GitReaderProtocol
from revu.infrastructure.git_providers.repository_files import (
    MAX_TREE_ENTRIES,
    decode,
    too_large,
)

logger = get_logger(name=__name__)


class GitCommandError(RuntimeError):
    """git refused a command. Its own message is the useful part, so it is kept."""


class LocalGitPort:
    """Reads the change and the code around it from a working tree."""

    def __init__(
        self,
        root: Path,
        base: str,
        head: str,
        host: GitReaderProtocol | None = None,
    ) -> None:
        self._root = Path(root)
        self._base = base
        self._head = head
        self._host = host

    async def fetch_diff(self, repo: str, index: int) -> str:
        """The change, as a code host would show it.

        Three dots, not two: `base..head` also contains everything that landed on
        the base branch since the fork point, and reviewing that would blame this
        author for other people's commits.
        """
        await self._require_merge_base()

        output = await self._git("diff", "--no-color", "--no-ext-diff", f"{self._base}...{self._head}")

        return decode(output)

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        """The earlier conversation, which only the host knows about."""
        if self._host is None:
            return None

        return await self._host.fetch_review_context(repo=repo, index=index)

    async def fetch_file(self, repo: str, path: str, revision: str) -> str | None:
        try:
            content = await self._git("show", f"{revision}:{path}")
        except GitCommandError:
            # Not in that revision. A working tree can still hold it: on a
            # developer's machine `--head HEAD` reviews work that is not committed.
            return self._read_from_disk(path)

        text = decode(content)

        return None if too_large(text) else text

    async def list_files(self, repo: str, revision: str) -> tuple[str, ...]:
        """Every blob of a revision, from git itself rather than from a walk."""
        output = await self._git("ls-tree", "-r", revision)
        paths: list[str] = []

        for line in decode(output).splitlines():
            meta, _, path = line.partition("\t")
            # `<mode> <type> <object>\t<path>`; a submodule is a commit, not a file.
            fields = meta.split()

            if path and len(fields) >= 2 and fields[1] == "blob":
                paths.append(path)

        return tuple(paths[:MAX_TREE_ENTRIES])

    async def _require_merge_base(self) -> None:
        """Fail with advice, not with an empty diff.

        A shallow checkout (`fetch-depth: 1`, `GIT_DEPTH`) has no merge base, and
        `git diff base...head` then answers with nothing at all — which would look
        like a pull request that changes nothing rather than a misconfigured job.
        """
        try:
            await self._git("merge-base", self._base, self._head)
        except GitCommandError as exc:
            raise GitCommandError(
                f"cannot compare {self._base!r} with {self._head!r}: {exc}. "
                "A shallow checkout has no common history — fetch the full history "
                "(`fetch-depth: 0` in GitHub and Gitea Actions, `GIT_DEPTH: 0` in GitLab CI)"
            ) from exc

    def _read_from_disk(self, path: str) -> str | None:
        """The file as it is on disk, if it is really inside the checkout."""
        root = self._root.resolve()
        candidate = (root / path).resolve()

        if not candidate.is_relative_to(root) or not candidate.is_file():
            return None

        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

        return None if too_large(text) else text

    async def _git(self, *args: str) -> bytes:
        """Run git in the checkout and hand back its stdout."""
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=self._root,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            raise GitCommandError("git is not installed, so a local checkout cannot be read") from exc

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            message = decode(stderr).strip() or "no output"

            raise GitCommandError(f"git {' '.join(args)} failed: {message}")

        return stdout


class StaticDiffReader:
    """A reader whose diff is given rather than computed.

    `--diff-file` replays a diff saved earlier — from another review, from a test,
    or from a machine with no checkout at all. Only the change is fixed: the files
    a deep review wants still come from the checkout through `inner`.
    """

    def __init__(self, diff: str, inner: GitReaderProtocol) -> None:
        self._diff = diff
        self._inner = inner

    async def fetch_diff(self, repo: str, index: int) -> str:
        return self._diff

    async def fetch_review_context(self, repo: str, index: int) -> ReviewContextDTO | None:
        return await self._inner.fetch_review_context(repo=repo, index=index)

    async def fetch_file(self, repo: str, path: str, revision: str) -> str | None:
        return await self._inner.fetch_file(repo=repo, path=path, revision=revision)

    async def list_files(self, repo: str, revision: str) -> tuple[str, ...]:
        return await self._inner.list_files(repo=repo, revision=revision)
