"""The command as a pipeline runs it: nothing on the command line, everything in the environment."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from revu.application.registry.git_connections import GitConnectionRegistry
from revu.domain.entities.dto.ai_provider_dto import (
    GitHubReviewCommentDTO,
    ReviewResponseDTO,
)
from revu.presentation.cli.review import (
    EXIT_FAILED,
    EXIT_FINDINGS,
    EXIT_OK,
    CliError,
    DiffSource,
    FailOn,
    OutputFormat,
    ReviewOptions,
    run_review,
)

pytestmark = pytest.mark.integration

AI_ENV = {
    "AI_PROVIDER_API_KEY": "secret",
    "AI_PROVIDER_MODEL": "gpt-4o-mini",
    "REVIEW_MODE": "inline",
}


def git(root: Path, *args: str) -> str:
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
    git(tmp_path, "init", "-b", "main")
    (tmp_path / "app.py").write_text("def run():\n    return 1\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-m", "first")
    git(tmp_path, "checkout", "-b", "feature")
    (tmp_path / "app.py").write_text("def run():\n    return 2\n")
    git(tmp_path, "commit", "-am", "change")

    return tmp_path


@pytest.fixture
def github_env(tmp_path, checkout) -> dict[str, str]:
    """What GitHub Actions hands a job, minus the token."""
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "pull_request": {
                    "number": 7,
                    "title": "Add feature",
                    "body": "Implements it",
                    "base": {"sha": git(checkout, "rev-parse", "main")},
                    "head": {"sha": git(checkout, "rev-parse", "feature")},
                }
            }
        ),
        encoding="utf-8",
    )

    return {
        **AI_ENV,
        "GITHUB_ACTIONS": "true",
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_SERVER_URL": "https://github.com",
    }


@pytest.fixture
def ai_port():
    port = AsyncMock()
    port.get_comment_response.return_value = "готово"
    port.get_inline_response.return_value = ReviewResponseDTO(general_comment="итог", comments=[])

    return port


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch, ai_port):
    """No network, and no key needed: the wiring is what these tests are about."""

    class Registry:
        def __init__(self, settings, http_client) -> None:
            self.settings = settings

        def for_connection(self, config):
            return ai_port

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr("revu.presentation.cli.review.AIProfileRegistry", Registry)

    return ai_port


@pytest.fixture
def host_port():
    """A host that answers nothing over the network but records what it was asked."""
    port = AsyncMock()
    port.fetch_review_context.return_value = None

    return port


@pytest.fixture
def fake_host(monkeypatch, host_port):
    """Keeps the real configuration, swaps the port that would talk to a host."""

    class Registry:
        def __init__(self, settings, http_client) -> None:
            self._real = GitConnectionRegistry(settings, http_client)

        def resolve(self, key):
            return replace(self._real.resolve(key), port=host_port)

    monkeypatch.setattr("revu.presentation.cli.review.GitConnectionRegistry", Registry)

    return host_port


async def test_a_ci_run_with_nothing_on_the_command_line_reviews_the_checkout(checkout, github_env, ai_port, capsys):
    """The claim the whole feature rests on: the environment is enough."""
    code = await run_review(ReviewOptions(root=checkout), github_env)

    assert code == EXIT_OK
    task = ai_port.get_inline_response.await_args.args[0]
    # Inline mode sends the diff with the line numbers the model must anchor to.
    assert "- [2]     return 1" in task.diff
    assert "+ [2]     return 2" in task.diff
    # The review is in the job log, because no token was given.
    assert "итог" in capsys.readouterr().out


async def test_the_run_says_what_it_is_reviewing(checkout, github_env, caplog):
    with caplog.at_level("INFO"):
        await run_review(ReviewOptions(root=checkout), github_env)

    assert "reviewing owner/repo#7: Add feature" in caplog.text
    assert "as github" in caplog.text
    assert "answer to StdoutPublisher" in caplog.text


async def test_the_run_reports_what_the_context_cost(checkout, github_env, caplog):
    with caplog.at_level("INFO"):
        await run_review(ReviewOptions(root=checkout), github_env)

    assert "review context for connection ci-run, owner/repo#7" in caplog.text


async def test_the_depth_flag_overrides_the_environment(checkout, github_env, caplog):
    with caplog.at_level("INFO"):
        await run_review(ReviewOptions(root=checkout, depth="deep"), github_env)

    assert "depth=deep" in caplog.text


@pytest.mark.parametrize(
    ("fail_on", "expected"),
    [(FailOn.NEVER, EXIT_OK), (FailOn.FINDINGS, EXIT_FINDINGS)],
)
async def test_findings_fail_the_pipeline_only_when_asked(
    checkout,
    github_env,
    ai_port,
    fail_on,
    expected,
):
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="тут")],
    )

    code = await run_review(ReviewOptions(root=checkout, fail_on=fail_on), github_env)

    assert code == expected


@pytest.mark.parametrize(
    ("fail_on", "expected"),
    [(FailOn.NEVER, EXIT_OK), (FailOn.ERROR, EXIT_FAILED), (FailOn.FINDINGS, EXIT_FAILED)],
)
async def test_a_review_that_could_not_be_done_is_fatal_only_when_asked(
    checkout,
    github_env,
    ai_port,
    fail_on,
    expected,
):
    ai_port.get_inline_response.side_effect = RuntimeError("the provider is down")

    code = await run_review(ReviewOptions(root=checkout, fail_on=fail_on), github_env)

    assert code == expected


async def test_a_token_turns_the_review_into_a_comment(checkout, github_env, fake_host):
    env = {**github_env, "GITHUB_TOKEN": "gh-token"}

    code = await run_review(ReviewOptions(root=checkout), env)

    assert code == EXIT_OK
    body = fake_host.send_inline.await_args.kwargs["review"].general_comment
    assert body.startswith("🤖 **ReVu**")
    assert "<!-- revu -->" in body


async def test_the_conversation_is_read_from_the_host_when_a_token_exists(checkout, github_env, fake_host):
    fake_host.fetch_review_context.return_value = None

    await run_review(ReviewOptions(root=checkout), {**github_env, "GITHUB_TOKEN": "gh-token"})

    fake_host.fetch_review_context.assert_awaited_once_with(repo="owner/repo", index=7)


async def test_without_a_token_the_host_is_not_asked_anything(checkout, github_env, fake_host):
    await run_review(ReviewOptions(root=checkout), github_env)

    fake_host.fetch_review_context.assert_not_awaited()
    fake_host.send_inline.assert_not_awaited()


async def test_a_read_only_token_refuses_to_comment(checkout, github_env, fake_host):
    """GitLab's job token reads a merge request and cannot write a note in it."""
    env = {
        **AI_ENV,
        "GITLAB_CI": "true",
        "CI_PROJECT_PATH": "group/project",
        "CI_MERGE_REQUEST_IID": "7",
        "CI_MERGE_REQUEST_DIFF_BASE_SHA": git(checkout, "rev-parse", "main"),
        "CI_COMMIT_SHA": git(checkout, "rev-parse", "feature"),
        "CI_SERVER_URL": "https://gitlab.example.com",
        "CI_JOB_TOKEN": "job-token",
    }

    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout, comment=True), env)

    assert "GIT_PROVIDER_USER_TOKEN" in str(caught.value)
    assert "project access token" in str(caught.value)


async def test_the_api_diff_source_needs_a_token(checkout, github_env, fake_host):
    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout, diff_source=DiffSource.API), github_env)

    assert "no token" in str(caught.value)


async def test_commenting_needs_a_repository(tmp_path, ai_port):
    env = {**AI_ENV, "GITLAB_CI": "true", "CI_JOB_TOKEN": "job-token"}

    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=tmp_path, comment=True), env)

    assert "--repo" in str(caught.value)


async def test_a_local_diff_needs_something_to_compare_against(checkout, github_env):
    env = {key: value for key, value in github_env.items() if key != "GITHUB_EVENT_PATH"}

    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout), env)

    assert "--base" in str(caught.value)
    assert "CI_MERGE_REQUEST_DIFF_BASE_SHA" in str(caught.value)


async def test_a_saved_diff_is_reviewed_without_asking_git(checkout, github_env, ai_port, tmp_path, capsys):
    saved = tmp_path / "saved.diff"
    saved.write_text(
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n context\n-old\n+new\n",
        encoding="utf-8",
    )
    # Comment mode is sent the diff as it is, so the saved text arrives unchanged.
    env = {**github_env, "CONTEXT_DEPTH": "flat", "REVIEW_MODE": "comment"}

    code = await run_review(ReviewOptions(root=checkout, diff_source=DiffSource.FILE, diff_file=saved), env)

    assert code == EXIT_OK
    assert ai_port.get_comment_response.await_args.args[0].diff == saved.read_text(encoding="utf-8")


async def test_a_missing_diff_file_is_a_usage_error(checkout, github_env):
    with pytest.raises(CliError) as caught:
        await run_review(
            ReviewOptions(root=checkout, diff_source=DiffSource.FILE, diff_file=checkout / "nope.diff"),
            github_env,
        )

    assert "cannot read the diff file" in str(caught.value)


async def test_the_json_format_prints_one_object(checkout, github_env, capsys):
    code = await run_review(
        ReviewOptions(root=checkout, output_format=OutputFormat.JSON),
        github_env,
    )

    assert code == EXIT_OK
    payload = json.loads(capsys.readouterr().out)

    assert payload["kind"] == "inline"
    assert payload["repo"] == "owner/repo"
    assert payload["number"] == 7


async def test_a_shallow_checkout_is_explained_to_the_user(tmp_path, checkout, github_env):
    shallow = tmp_path / "shallow"
    git(checkout, "clone", "--depth", "1", "--branch", "feature", f"file://{checkout}", str(shallow))

    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=shallow), github_env)

    assert "fetch-depth: 0" in str(caught.value)


async def test_outside_ci_the_provider_has_to_be_named(checkout, tmp_path):
    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout), AI_ENV)

    assert "--provider" in str(caught.value)


async def test_outside_ci_a_review_can_still_be_run_by_hand(checkout, ai_port):
    """The same command, driven from a developer's machine: a saved diff and a log."""
    env = {
        **AI_ENV,
        "GIT_PROVIDER": "github",
        "GIT_PROVIDER_USER_TOKEN": "personal-token",
        "CONTEXT_DEPTH": "flat",
    }

    code = await run_review(
        ReviewOptions(root=checkout, base="main", head="feature", comment=False),
        env,
    )

    assert code == EXIT_OK
    assert ai_port.get_inline_response.await_count == 1


async def test_a_configuration_mistake_is_a_usage_error_not_a_failed_review(checkout, github_env):
    """The user can fix a missing key; a "review could not be completed" hides it."""
    env = {key: value for key, value in github_env.items() if key != "AI_PROVIDER_API_KEY"}

    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout), env)

    assert "AI_PROVIDER_API_KEY" in str(caught.value)


async def test_the_api_diff_source_reads_through_the_host(checkout, github_env, fake_host):
    fake_host.fetch_diff.return_value = (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,2 +1,2 @@\n context\n-old\n+new\n"
    )
    env = {**github_env, "GITHUB_TOKEN": "gh-token", "REVIEW_MODE": "comment", "CONTEXT_DEPTH": "flat"}

    code = await run_review(ReviewOptions(root=checkout, diff_source=DiffSource.API), env)

    assert code == EXIT_OK
    fake_host.fetch_diff.assert_awaited_once_with(repo="owner/repo", index=7)


async def test_the_file_source_needs_a_file(checkout, github_env):
    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout, diff_source=DiffSource.FILE), github_env)

    assert "--diff-file" in str(caught.value)


async def test_commenting_without_a_token_at_all_is_refused(checkout, github_env):
    with pytest.raises(CliError) as caught:
        await run_review(ReviewOptions(root=checkout, comment=True), github_env)

    assert "no token for commenting" in str(caught.value)


async def test_the_code_quality_report_is_written_and_the_review_is_still_printed(
    checkout,
    github_env,
    ai_port,
    tmp_path,
    capsys,
):
    """GitLab's answer to a read-only job token: findings as an artifact, not a note."""
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="тут")],
    )
    report = tmp_path / "reports" / "codequality.json"

    code = await run_review(
        ReviewOptions(root=checkout, output_format=OutputFormat.GITLAB_CODEQUALITY, output=report),
        github_env,
    )

    assert code == EXIT_OK
    assert json.loads(report.read_text(encoding="utf-8"))[0]["location"]["path"] == "app.py"
    assert "итог" in capsys.readouterr().out


async def test_annotations_are_printed_for_the_runner_to_turn_into_marks(
    checkout,
    github_env,
    ai_port,
    capsys,
):
    ai_port.get_inline_response.return_value = ReviewResponseDTO(
        general_comment="итог",
        comments=[GitHubReviewCommentDTO(path="app.py", line=2, side="RIGHT", body="тут")],
    )

    code = await run_review(ReviewOptions(root=checkout, output_format=OutputFormat.GITHUB_ANNOTATIONS), github_env)

    assert code == EXIT_OK
    assert "::warning file=app.py,line=2,endLine=2,title=ReVu::тут" in capsys.readouterr().out


async def test_the_review_reaches_the_log_and_the_pull_request(
    checkout,
    github_env,
    fake_host,
    capsys,
):
    """Both destinations, because a reviewer reads the job and the author reads the PR."""
    await run_review(
        ReviewOptions(root=checkout, comment=True),
        {**github_env, "GITHUB_TOKEN": "gh-token"},
    )

    fake_host.send_inline.assert_awaited_once()
    assert "итог" in capsys.readouterr().out


async def test_a_failed_review_says_so_in_the_pull_request(checkout, github_env, fake_host, ai_port):
    """Otherwise a red job is all anyone sees, with no idea what happened."""
    ai_port.get_inline_response.side_effect = RuntimeError("the provider is down")

    code = await run_review(
        ReviewOptions(root=checkout, comment=True),
        {**github_env, "GITHUB_TOKEN": "gh-token"},
    )

    assert code == EXIT_OK  # --fail-on is never by default
    notice = fake_host.send_comment.await_args.kwargs["review"]
    assert "ReVu не смог выполнить ревью" in notice
    assert "перезапустив job" in notice


async def test_the_failure_notice_can_be_turned_off(checkout, github_env, fake_host, ai_port):
    ai_port.get_inline_response.side_effect = RuntimeError("the provider is down")

    await run_review(
        ReviewOptions(root=checkout, comment=True),
        {**github_env, "GITHUB_TOKEN": "gh-token", "NOTIFY_ON_FAILURE": "false"},
    )

    fake_host.send_comment.assert_not_awaited()


async def test_without_a_token_a_failure_stays_in_the_log(checkout, github_env, fake_host, ai_port):
    ai_port.get_inline_response.side_effect = RuntimeError("the provider is down")

    await run_review(ReviewOptions(root=checkout), github_env)

    fake_host.send_comment.assert_not_awaited()


async def test_a_failure_notice_that_cannot_be_posted_does_not_hide_the_failure(
    checkout,
    github_env,
    fake_host,
    ai_port,
    caplog,
):
    """Best effort by design: it must not mask the error that caused it."""
    ai_port.get_inline_response.side_effect = RuntimeError("the provider is down")
    fake_host.send_comment.side_effect = RuntimeError("and the host is too")

    with caplog.at_level("ERROR"):
        code = await run_review(
            ReviewOptions(root=checkout, comment=True),
            {**github_env, "GITHUB_TOKEN": "gh-token"},
        )

    assert code == EXIT_OK
    assert "could not publish the failure notice" in caplog.text
