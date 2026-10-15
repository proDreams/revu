"""The `revu review` command: one review, and an exit code that says what happened.

Everything the run needs comes from the environment the pipeline provides, so the
common case is a job with no arguments at all. The command line exists to override
what the platform said, or to run the same review by hand on a developer's machine.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

from revu.application.config import get_logger
from revu.application.entities.config import ConfigError, GitConnectionConfig
from revu.application.registry.ai_profiles import AIProfileRegistry
from revu.application.registry.git_connections import GitConnectionRegistry
from revu.application.services.context_builder import ContextBuilder
from revu.application.services.failure_notice import access_hint, failure_notice
from revu.application.services.review_runner import (
    ReviewRequest,
    ReviewRunner,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.protocols.comment_publisher_protocol import CommentPublisherProtocol
from revu.domain.protocols.git_reader_protocol import GitReaderProtocol
from revu.infrastructure.code_analysis.tree_sitter_parser import TreeSitterCodeParser
from revu.infrastructure.git_providers.local import (
    GitCommandError,
    LocalGitPort,
    StaticDiffReader,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway
from revu.infrastructure.publishers.composite_publisher import combine_publishers
from revu.infrastructure.publishers.github_annotation_publisher import (
    GitHubAnnotationPublisher,
)
from revu.infrastructure.publishers.gitlab_codequality_publisher import (
    GitLabCodeQualityPublisher,
)
from revu.infrastructure.publishers.json_publisher import JsonPublisher
from revu.infrastructure.publishers.stdout_publisher import StdoutPublisher
from revu.presentation.cli.environment import CiEnvironment, detect
from revu.presentation.cli.settings_from_env import CONNECTION_KEY, build_settings

logger = get_logger(name=__name__)

#: 0 — nothing to answer for; 1 — findings, and the gate was asked to react to them;
#: 2 — the review itself could not be done.
EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_FAILED = 2

#: Where the code quality report goes when `--output` is not given. GitLab reads it
#: from wherever `artifacts:reports:codequality` points, so the path is the user's
#: to choose; this is the name the examples use.
DEFAULT_REPORT_PATH = Path("revu-codequality.json")

#: A pipeline is retried by restarting the job, which a server has no way to say.
CI_RETRY_HINT = "Ревью можно перезапустить, перезапустив job."


class CliError(RuntimeError):
    """Something the command cannot do, said in words a user can act on."""


class DiffSource(StrEnum):
    """Where the change comes from."""

    GIT = "git"
    API = "api"
    FILE = "file"


class FailOn(StrEnum):
    """When the review should fail the pipeline."""

    NEVER = "never"
    ERROR = "error"
    FINDINGS = "findings"


class OutputFormat(StrEnum):
    """How the review is written out."""

    TEXT = "text"
    JSON = "json"
    GITLAB_CODEQUALITY = "gitlab-codequality"
    GITHUB_ANNOTATIONS = "github-annotations"


@dataclass(frozen=True, slots=True)
class ReviewOptions:
    """What the command line asked for, before the environment has its say."""

    diff_source: DiffSource = DiffSource.GIT
    fail_on: FailOn = FailOn.NEVER
    output_format: OutputFormat = OutputFormat.TEXT
    #: ``None`` means "comment when a token allows it, otherwise print".
    comment: bool | None = None
    #: Where a report is written, when the format asks for one.
    output: Path | None = None
    depth: str | None = None
    base: str | None = None
    head: str | None = None
    diff_file: Path | None = None
    repo: str | None = None
    number: int | None = None
    provider: GitProviderEnum | None = None
    root: Path = Path()


async def run_review(options: ReviewOptions, env: Mapping[str, str] | None = None) -> int:
    """Run one review and report, by exit code, what came of it."""
    variables = _with_overrides(options, _environment_variables(env))
    environment = _environment(options, variables)
    base, head = _revisions(environment, options)

    try:
        settings = build_settings(environment, variables)
    except ConfigError as exc:
        # A configuration mistake is the user's to fix, so it is said in one line
        # rather than hidden inside a review that "could not be completed".
        raise CliError(str(exc)) from exc

    http_client = HttpClientGateway(settings=settings.http)
    profiles = AIProfileRegistry(settings, http_client)

    connection = GitConnectionRegistry(settings, http_client).resolve(CONNECTION_KEY)
    host = connection.port

    try:
        reader = _reader(options, environment, host, base, head)
        publisher = _publishers(options, environment, host)

        logger.info(
            "reviewing %s#%s: %s as %s, diff from %s, answer to %s",
            environment.repo or "(no repository)",
            environment.number or "?",
            environment.title or "(no title)",
            environment.name,
            options.diff_source.value,
            type(publisher).__name__,
        )

        outcome = await ReviewRunner(context_builder=ContextBuilder(parser=TreeSitterCodeParser())).run(
            reader=reader,
            publisher=publisher,
            ai_port=profiles.for_connection(connection.config),
            config=connection.config,
            request=ReviewRequest(
                repo=environment.repo,
                number=environment.number or 0,
                title=environment.title,
                body=environment.body,
                revision=environment.head or head,
            ),
        )
    except CliError:
        # A usage error raised while building the run must reach the caller as
        # itself, not become a "review could not be completed" with an exit code.
        raise
    except GitCommandError as exc:
        raise CliError(str(exc)) from exc
    except Exception as exc:
        if hint := access_hint(connection.config.host, exc):
            logger.warning("%s", hint)

        logger.exception("the review could not be completed")
        await _notify_failure(connection.config, environment, host, exc)

        return EXIT_OK if options.fail_on is FailOn.NEVER else EXIT_FAILED
    finally:
        await profiles.aclose()
        await http_client.aclose()

    if options.fail_on is FailOn.FINDINGS and outcome.findings:
        logger.error("%d finding(s) reported, and --fail-on findings was asked for", outcome.findings)

        return EXIT_FINDINGS

    return EXIT_OK


def _environment_variables(env: Mapping[str, str] | None) -> dict[str, str]:
    return dict(os.environ if env is None else env)


def _with_overrides(options: ReviewOptions, env: dict[str, str]) -> dict[str, str]:
    """The command line beats the environment, which is what an override means.

    ``env`` is the copy the caller owns, so it is edited in place.
    """
    if options.depth:
        env["CONTEXT_DEPTH"] = options.depth

    return env


def _environment(options: ReviewOptions, env: Mapping[str, str]) -> CiEnvironment:
    """What the platform says, with the command line applied on top of it."""
    detected = detect(env)
    provider = options.provider or (detected.provider if detected else _provider_from_environment(env))

    if detected is None:
        if provider is None:
            raise CliError(
                "no continuous integration detected: pass --provider (and --repo for a review that "
                "comments), or run this inside GitHub Actions, GitLab CI or Gitea Actions"
            )

        detected = CiEnvironment(
            name="local",
            provider=provider,
            repo="",
            api_url=env.get("GIT_PROVIDER_URL") or None,
            token=env.get("GIT_PROVIDER_USER_TOKEN") or None,
        )

    repo = options.repo or detected.repo

    if not repo and options.comment:
        raise CliError("--comment needs a repository: pass --repo owner/name")

    return replace(
        detected,
        provider=provider or detected.provider,
        repo=repo,
        number=options.number or detected.number,
        base=options.base or detected.base,
        head=options.head or detected.head,
    )


def _provider_from_environment(env: Mapping[str, str]) -> GitProviderEnum | None:
    value = (env.get("GIT_PROVIDER") or "").strip().lower()

    return GitProviderEnum(value) if value in {item.value for item in GitProviderEnum} else None


def _revisions(environment: CiEnvironment, options: ReviewOptions) -> tuple[str, str]:
    """The two refs to compare, or a sentence saying which one is missing."""
    head = environment.head or "HEAD"

    if options.diff_source is DiffSource.GIT and not environment.base:
        raise CliError(
            "nothing to compare against: pass --base, or run where the platform provides one "
            "(CI_MERGE_REQUEST_DIFF_BASE_SHA in GitLab CI, the pull request payload in GitHub Actions)"
        )

    return environment.base or head, head


def _reader(
    options: ReviewOptions,
    environment: CiEnvironment,
    host: GitReaderProtocol,
    base: str,
    head: str,
) -> GitReaderProtocol:
    """Where the change is read from.

    The earlier conversation is not in a checkout, so whenever a token exists the
    local reader is given the host reader to answer that one question with.
    """
    if options.diff_source is DiffSource.API:
        _require_token(environment, "reading the diff from the API")

        return host

    conversation = host if environment.token else None

    if options.diff_source is DiffSource.FILE:
        if options.diff_file is None:
            raise CliError("--diff-source file needs --diff-file")

        try:
            saved = options.diff_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise CliError(f"cannot read the diff file {options.diff_file}: {exc}") from exc

        return StaticDiffReader(diff=saved, inner=LocalGitPort(root=options.root, base=head, head=head))

    return LocalGitPort(root=options.root, base=base, head=head, host=conversation)


def _publishers(
    options: ReviewOptions,
    environment: CiEnvironment,
    host: CommentPublisherProtocol,
) -> CommentPublisherProtocol:
    """Everywhere the review goes.

    Two things are chosen here: a format that only a machine reads (JSON, or a
    report that carries the findings into the merge request widget without asking
    anyone for permission), and whether a comment may be left under the pull
    request. The job log always gets the review — that is where a person looks when
    something is off, and it costs nothing.
    """
    if options.output_format is OutputFormat.JSON:
        return JsonPublisher()

    destinations: list[CommentPublisherProtocol] = []

    match options.output_format:
        case OutputFormat.GITLAB_CODEQUALITY:
            destinations.append(GitLabCodeQualityPublisher(path=options.output or DEFAULT_REPORT_PATH))
        case OutputFormat.GITHUB_ANNOTATIONS:
            destinations.append(GitHubAnnotationPublisher())

    wants_comment = options.comment
    if wants_comment is None:
        wants_comment = bool(environment.token) and not environment.token_is_read_only

    if wants_comment:
        # A comment is an API call, so a token is not optional here — whether the
        # user asked for it or the default decided it.
        _require_token(environment, "commenting on the pull request")

        if environment.token_is_read_only:
            raise CliError(
                "this token may read a merge request but not comment on it: GitLab's CI job token "
                "cannot write notes. Set GIT_PROVIDER_USER_TOKEN to a project access token, or drop "
                "--comment and let the review go to the job log"
            )

        destinations.append(host)

    destinations.append(StdoutPublisher())

    return combine_publishers(*destinations)


async def _notify_failure(
    config: GitConnectionConfig,
    environment: CiEnvironment,
    host: CommentPublisherProtocol,
    exc: BaseException,
) -> None:
    """Tell the pull request that the review failed, the way the server does.

    Best effort, like the server's own notice: a failing notice is logged, never
    raised, so it cannot mask the original error. It is skipped when nothing may
    comment — a log line is all a job can offer then.
    """
    if not config.notify_on_failure:
        return

    if not environment.token or environment.token_is_read_only or not environment.number or not environment.repo:
        logger.info("not publishing a failure notice for %s: nothing here may comment", environment.repo or "?")

        return

    try:
        await host.send_comment(
            repo_owner=environment.repo,
            review=failure_notice(exc, retry_hint=CI_RETRY_HINT),
            index=environment.number,
        )
    except Exception:
        logger.exception("could not publish the failure notice for %s#%s", environment.repo, environment.number)


def _require_token(environment: CiEnvironment, what: str) -> None:
    if not environment.token:
        raise CliError(
            f"no token for {what}: set GIT_PROVIDER_USER_TOKEN (GitHub Actions passes "
            "secrets.GITHUB_TOKEN into the job, GitLab CI has CI_JOB_TOKEN and CI_PROJECT_PATH)"
        )
