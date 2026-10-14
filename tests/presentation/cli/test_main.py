"""The command line itself: arguments, dispatch, and the exit code it returns."""

import importlib.metadata
import runpy
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.presentation.cli.main import (
    EXIT_FAILED,
    build_parser,
    main,
    options_from_args,
    version,
)
from revu.presentation.cli.review import DiffSource, FailOn, OutputFormat

pytestmark = pytest.mark.unit


def parse(*argv: str):
    return options_from_args(build_parser().parse_args(["review", *argv]))


def test_a_review_needs_no_arguments_at_all():
    options = parse()

    assert options.diff_source is DiffSource.GIT
    assert options.fail_on is FailOn.NEVER
    assert options.output_format is OutputFormat.TEXT
    assert options.comment is None
    assert options.provider is None


def test_a_diff_file_is_a_diff_source_of_its_own():
    options = parse("--diff-file", "saved.diff")

    assert options.diff_source is DiffSource.FILE
    assert str(options.diff_file) == "saved.diff"


def test_stdout_and_comment_are_stated_explicitly():
    assert parse("--stdout").comment is False
    assert parse("--comment").comment is True


def test_every_override_reaches_the_options():
    options = parse(
        "--provider",
        "gitea",
        "--repo",
        "owner/repo",
        "--pr",
        "5",
        "--base",
        "main",
        "--head",
        "feature",
        "--depth",
        "deep",
        "--fail-on",
        "findings",
        "--format",
        "json",
    )

    assert options.provider is GitProviderEnum.GITEA
    assert options.repo == "owner/repo"
    assert options.number == 5
    assert (options.base, options.head) == ("main", "feature")
    assert options.depth == "deep"
    assert options.fail_on is FailOn.FINDINGS
    assert options.output_format is OutputFormat.JSON


def test_json_and_a_comment_contradict_each_other(capsys):
    """Contradictory, but both are valid arguments, so the command answers for it."""
    code = main(["review", "--format", "json", "--comment"])

    assert code == EXIT_FAILED
    assert "contradict each other" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["review", "--comment", "--stdout"],
        ["review", "--provider", "sourceforge"],
        ["review", "--depth", "infinite"],
        ["review", "--fail-on", "sometimes"],
        ["nonsense"],
    ],
)
def test_arguments_that_cannot_be_honoured_stop_with_usage(argv):
    with pytest.raises(SystemExit) as caught:
        main(argv)

    assert caught.value.code == 2


def test_a_usage_error_is_printed_once_and_exits_with_two(capsys):
    code = main(["review", "--format", "json", "--comment"])

    assert code == EXIT_FAILED
    assert "revu: --comment and --format json contradict each other" in capsys.readouterr().err


def test_version_is_the_installed_package():
    assert version() == importlib.metadata.version("revu")


def test_version_survives_a_source_tree_that_was_never_installed(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)

    assert version() == "unknown"


def test_the_version_command_prints_it(capsys):
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == version()


def test_serve_starts_the_webhook_server(monkeypatch):
    started = MagicMock()
    monkeypatch.setattr("revu.application.app.run_app", started)

    assert main(["serve"]) == 0
    started.assert_called_once_with()


def test_a_review_is_handed_to_the_command(monkeypatch):
    """`main` must not reimplement anything: it parses and hands over.

    Synchronous on purpose: the command runs the review with `asyncio.run`, which
    cannot be called from inside a loop that is already running.
    """
    from revu.presentation.cli import main as cli

    run = AsyncMock(return_value=0)
    monkeypatch.setattr(cli, "run_review", run)

    assert cli.main(["review", "--stdout"]) == 0
    assert run.await_args.args[0].comment is False


def test_the_package_can_be_run_as_a_module(monkeypatch, capsys):
    """`python -m revu` is how a container without the script on PATH calls it."""
    monkeypatch.setattr(sys, "argv", ["revu", "version"])

    with pytest.raises(SystemExit) as caught:
        runpy.run_module("revu", run_name="__main__")

    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == version()
