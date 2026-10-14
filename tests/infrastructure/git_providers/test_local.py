"""Reading a change out of a real checkout, with a real git."""

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from revu.domain.entities.dto.review_context_dto import (
    PreviousCommentDTO,
    ReviewContextDTO,
)
from revu.infrastructure.git_providers.local import (
    GitCommandError,
    LocalGitPort,
    StaticDiffReader,
)

pytestmark = pytest.mark.integration

REPO = "owner/repo"


def git(root: Path, *args: str) -> str:
    """Run git with an identity of its own, so a developer's config cannot leak in."""
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.email=revu@example.com",
            "-c",
            "user.name=ReVu",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """A repository where main moved on after the feature branch forked."""
    git(tmp_path, "init", "-b", "main")
    (tmp_path / "app.py").write_text("def run():\n    return 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "first")

    git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "app.py").write_text("def run():\n    return 2\n")
    git(tmp_path, "commit", "-am", "the change under review")

    # Unrelated work that landed on main afterwards: a two-dot diff would drag it in.
    git(tmp_path, "checkout", "main")
    (tmp_path / "other.py").write_text("x = 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "someone else's work")
    git(tmp_path, "checkout", "feature")

    return tmp_path


def rev(root: Path, ref: str) -> str:
    return git(root, "rev-parse", ref)


@pytest.fixture
def port(checkout: Path) -> LocalGitPort:
    return LocalGitPort(root=checkout, base="main", head="feature")


async def test_the_diff_stops_at_the_fork_point(port, checkout):
    """Other people's commits on the base branch are not this author's change."""
    diff = await port.fetch_diff(repo=REPO, index=1)

    assert "app.py" in diff
    assert "other.py" not in diff
    # `def run():` is unchanged, so it travels as a context line; only the body
    # of the function differs.
    assert "-    return 1" in diff
    assert "+    return 2" in diff


async def test_a_file_is_read_at_the_revision_asked_for(port, checkout):
    base = rev(checkout, "main")
    head = rev(checkout, "feature")

    assert "return 1" in await port.fetch_file(repo=REPO, path="app.py", revision=base)
    assert "return 2" in await port.fetch_file(repo=REPO, path="app.py", revision=head)


async def test_a_missing_path_is_an_answer_not_a_failure(port):
    assert await port.fetch_file(repo=REPO, path="does/not/exist.py", revision="HEAD") is None


async def test_uncommitted_work_is_read_from_disk(port, checkout):
    """`--head HEAD` on a developer's machine reviews what is not committed yet."""
    (checkout / "fresh.py").write_text("x = 1\n")

    assert await port.fetch_file(repo=REPO, path="fresh.py", revision="HEAD") == "x = 1\n"


async def test_a_path_outside_the_checkout_is_refused(port):
    """A path comes out of a diff, and a diff is attacker-controlled text."""
    assert await port.fetch_file(repo=REPO, path="../../../../etc/passwd", revision="HEAD") is None


async def test_a_file_past_the_size_limit_is_not_read(port, checkout):
    (checkout / "big.py").write_text("x = 1\n" * 40_000)
    git(checkout, "add", "-A")
    git(checkout, "commit", "-m", "a big generated file")
    (checkout / "uncommitted_big.py").write_text("y = 1\n" * 40_000)

    assert await port.fetch_file(repo=REPO, path="big.py", revision="HEAD") is None
    assert await port.fetch_file(repo=REPO, path="uncommitted_big.py", revision="HEAD") is None


async def test_the_tree_lists_files_and_nothing_else(port):
    paths = await port.list_files(repo=REPO, revision="feature")

    assert paths == ("app.py",)


async def test_the_tree_is_capped(monkeypatch, port):
    monkeypatch.setattr("revu.infrastructure.git_providers.local.MAX_TREE_ENTRIES", 0)

    assert await port.list_files(repo=REPO, revision="feature") == ()


async def test_a_shallow_checkout_says_what_to_do(tmp_path, checkout):
    """The most likely misconfiguration in CI, and the least obvious symptom."""
    shallow = tmp_path / "shallow"
    git(checkout, "clone", "--depth", "1", "--branch", "feature", f"file://{checkout}", str(shallow))
    port = LocalGitPort(root=shallow, base="main", head="HEAD")

    with pytest.raises(GitCommandError) as caught:
        await port.fetch_diff(repo=REPO, index=1)

    assert "fetch-depth: 0" in str(caught.value)
    assert "GIT_DEPTH: 0" in str(caught.value)


async def test_a_broken_revision_is_reported_not_swallowed(port):
    with pytest.raises(GitCommandError):
        await port.list_files(repo=REPO, revision="nonsense-ref")


async def test_missing_git_is_explained(monkeypatch, port):
    async def refuse(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("asyncio.create_subprocess_exec", refuse)

    with pytest.raises(GitCommandError) as caught:
        await port.list_files(repo=REPO, revision="HEAD")

    assert "git is not installed" in str(caught.value)


async def test_the_earlier_conversation_comes_from_the_host(checkout):
    """A checkout has no pull request comments in it; the host does."""
    host = AsyncMock()
    host.fetch_review_context.return_value = ReviewContextDTO(
        comments=[PreviousCommentDTO(author="revu", body="<!-- revu --> earlier", is_revu=True)],
    )
    port = LocalGitPort(root=checkout, base="main", head="feature", host=host)

    context = await port.fetch_review_context(repo=REPO, index=7)

    host.fetch_review_context.assert_awaited_once_with(repo=REPO, index=7)
    assert context is not None
    # The body is exactly what the host returned: cleaning is the host port's job.
    assert "earlier" in context.findings[0].body


async def test_without_a_host_there_is_no_conversation(checkout):
    port = LocalGitPort(root=checkout, base="main", head="feature")

    assert await port.fetch_review_context(repo=REPO, index=7) is None


async def test_a_file_that_cannot_be_read_is_not_a_crash(monkeypatch, port, checkout):
    """A review must not die because one file is unreadable.

    Simulated rather than done with permissions: a test suite that runs as root can
    read a file with no mode bits, so the real thing would pass here and fail there.
    """
    (checkout / "locked.py").write_text("x = 1\n")

    def refuse(*args, **kwargs):
        raise PermissionError("no")

    monkeypatch.setattr(Path, "read_text", refuse)

    assert await port.fetch_file(repo=REPO, path="locked.py", revision="HEAD") is None


async def test_a_saved_diff_replaces_only_the_change():
    """`--diff-file` fixes the diff; the files still come from the checkout."""
    inner = AsyncMock()
    inner.fetch_file.return_value = "file text"
    inner.list_files.return_value = ("a.py",)
    inner.fetch_review_context.return_value = None
    reader = StaticDiffReader(diff="the saved diff", inner=inner)

    assert await reader.fetch_diff(repo=REPO, index=1) == "the saved diff"
    assert await reader.fetch_file(repo=REPO, path="a.py", revision="HEAD") == "file text"
    assert await reader.list_files(repo=REPO, revision="HEAD") == ("a.py",)
    assert await reader.fetch_review_context(repo=REPO, index=1) is None
