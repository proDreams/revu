"""The command line: `revu review` for a pipeline, `revu serve` for a server.

Two ways into the same review. A pipeline runs `review` with no arguments at all,
because the environment it runs in already says everything; `serve` is the webhook
server it has always been.
"""

import argparse
import asyncio
import importlib.metadata
import sys
from collections.abc import Sequence
from pathlib import Path

from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.presentation.cli.review import (
    EXIT_FAILED,
    CliError,
    DiffSource,
    FailOn,
    OutputFormat,
    ReviewOptions,
    run_review,
)


def version() -> str:
    """The version of the package that is running.

    Read from the installed distribution rather than from a constant, so the answer
    is the image that was actually pulled — which is the whole point of asking in a
    pipeline.
    """
    try:
        return importlib.metadata.version("revu")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="revu",
        description="Проверяет изменения через ИИ и публикует ревью.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    review = commands.add_parser(
        "review",
        help="проверить diff и опубликовать ревью",
        description=(
            "Проверяет изменения и публикует ревью. В пайплайне аргументы не нужны: "
            "GitHub Actions, GitLab CI и Gitea Actions определяются по переменным окружения."
        ),
    )
    review.add_argument(
        "--diff-source",
        choices=[item.value for item in DiffSource],
        default=DiffSource.GIT.value,
        help="откуда брать diff: git (локальный чекаут, по умолчанию), api (через хостинг), file (--diff-file)",
    )
    review.add_argument("--diff-file", type=Path, help="файл с готовым diff (включает --diff-source file)")
    review.add_argument("--repo", help="репозиторий вида owner/name, если окружение его не сообщает")
    review.add_argument("--pr", type=int, dest="number", help="номер PR/MR, если окружение его не сообщает")
    review.add_argument("--base", help="ревизия, с которой сравнивать (по умолчанию — из окружения CI)")
    review.add_argument("--head", help="ревизия с изменениями (по умолчанию HEAD из окружения CI)")
    review.add_argument(
        "--provider",
        choices=[item.value for item in GitProviderEnum],
        help="git-хостинг; вне CI обязателен",
    )
    review.add_argument(
        "--depth",
        choices=["flat", "deep"],
        help="глубина контекста, переопределяет CONTEXT_DEPTH",
    )
    review.add_argument(
        "--fail-on",
        choices=[item.value for item in FailOn],
        default=FailOn.NEVER.value,
        help="когда ронять job: never (по умолчанию), error (ревью не состоялось), findings (есть замечания)",
    )
    review.add_argument(
        "--format",
        choices=[item.value for item in OutputFormat],
        default=OutputFormat.TEXT.value,
        help="формат вывода: text (по умолчанию) или json",
    )
    destination = review.add_mutually_exclusive_group()
    destination.add_argument("--comment", action="store_true", help="опубликовать ревью комментарием в PR/MR")
    destination.add_argument("--stdout", action="store_true", help="напечатать ревью, ничего не публикуя")

    commands.add_parser("serve", help="запустить сервер вебхуков")
    commands.add_parser("version", help="показать версию")

    return parser


def options_from_args(args: argparse.Namespace) -> ReviewOptions:
    """Turn parsed arguments into what the command acts on."""
    diff_source = DiffSource.FILE if args.diff_file else DiffSource(args.diff_source)

    if args.format == OutputFormat.JSON.value and args.comment:
        raise CliError("--comment and --format json contradict each other: json goes to the command's output")

    comment: bool | None = None
    if args.comment:
        comment = True
    elif args.stdout:
        comment = False

    return ReviewOptions(
        diff_source=diff_source,
        fail_on=FailOn(args.fail_on),
        output_format=OutputFormat(args.format),
        comment=comment,
        depth=args.depth,
        base=args.base,
        head=args.head,
        diff_file=args.diff_file,
        repo=args.repo,
        number=args.number,
        provider=GitProviderEnum(args.provider) if args.provider else None,
        root=Path(),
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the `revu` command."""
    args = build_parser().parse_args(argv)

    if args.command == "version":
        print(version())

        return 0

    if args.command == "serve":
        from revu.application.app import run_app

        run_app()

        return 0

    try:
        return asyncio.run(run_review(options_from_args(args)))
    except CliError as exc:
        print(f"revu: {exc}", file=sys.stderr)

        return EXIT_FAILED
