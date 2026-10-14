"""What a CI platform says about the change under review.

Each platform announces itself with its own variables, and the mapping from those
names to a review is the whole job of this module. Nothing here decides anything:
it gathers, so that a mistake in reading a variable is one test away from being
caught rather than buried in a pipeline.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from revu.application.config import get_logger
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum

logger = get_logger(name=__name__)

#: Where Gitea serves its API, and where GitHub Enterprise serves its own.
GITEA_API_SUFFIX = "/api/v1"
GITHUB_ENTERPRISE_API_SUFFIX = "/api/v3"

#: Variables that name the host explicitly, in the order they are trusted.
PROVIDER_OVERRIDES = ("GIT_PROVIDER", "REVU_PROVIDER")


@dataclass(frozen=True, slots=True)
class CiEnvironment:
    """One change, as the platform describes it."""

    #: Platform name for logs: ``github``, ``gitlab`` or ``gitea``.
    name: str
    provider: GitProviderEnum
    #: Repository as the host spells it, ``owner/name``.
    repo: str
    #: Pull request (merge request) number, when the run belongs to one.
    number: int | None = None
    title: str = ""
    body: str | None = None
    #: The refs to compare. Both are needed for a local diff.
    base: str | None = None
    head: str | None = None
    #: API root of the host, in the form each port expects.
    api_url: str | None = None
    token: str | None = None
    #: True when the token the platform handed us may read but never write.
    token_is_read_only: bool = False


def detect(env: Mapping[str, str]) -> CiEnvironment | None:
    """Recognise the platform from its variables, or return ``None`` outside CI."""
    if env.get("GITLAB_CI"):
        return _gitlab(env)

    if env.get("GITHUB_ACTIONS") or env.get("GITEA_ACTIONS"):
        return _github_compatible(env)

    return None


def _gitlab(env: Mapping[str, str]) -> CiEnvironment:
    # The job token may read a merge request and its notes but not write one, so a
    # project access token has to win when both are present.
    job_token = env.get("CI_JOB_TOKEN") or ""
    token = env.get("GIT_PROVIDER_USER_TOKEN") or env.get("GITLAB_TOKEN") or job_token or None
    iid = (env.get("CI_MERGE_REQUEST_IID") or "").strip()

    return CiEnvironment(
        name="gitlab",
        provider=GitProviderEnum.GITLAB,
        repo=env.get("CI_PROJECT_PATH") or "",
        number=int(iid) if iid.isdigit() else None,
        title=env.get("CI_MERGE_REQUEST_TITLE") or "",
        body=env.get("CI_MERGE_REQUEST_DESCRIPTION") or None,
        # The base of the *diff*, which is not the head of the target branch: the
        # latter is empty outside merged-results pipelines.
        base=env.get("CI_MERGE_REQUEST_DIFF_BASE_SHA") or None,
        head=env.get("CI_COMMIT_SHA") or None,
        api_url=env.get("CI_SERVER_URL") or None,
        token=token,
        token_is_read_only=bool(token) and token == job_token and not env.get("GIT_PROVIDER_USER_TOKEN"),
    )


def _github_compatible(env: Mapping[str, str]) -> CiEnvironment:
    """GitHub Actions, and Gitea Actions, which speaks the same language."""
    event = _read_event(env.get("GITHUB_EVENT_PATH"))
    pull_request = _as_mapping(event.get("pull_request"))
    api_url = env.get("GITHUB_API_URL") or ""
    provider = _github_provider(env, api_url)
    number = pull_request.get("number")

    return CiEnvironment(
        name="gitea" if provider is GitProviderEnum.GITEA else "github",
        provider=provider,
        repo=env.get("GITHUB_REPOSITORY") or "",
        number=int(number) if isinstance(number, int) else None,
        title=_text(pull_request.get("title")),
        body=_text(pull_request.get("body")) or None,
        base=_text(_as_mapping(pull_request.get("base")).get("sha")) or None,
        head=_text(_as_mapping(pull_request.get("head")).get("sha")) or None,
        api_url=_github_api_url(provider, api_url, env.get("GITHUB_SERVER_URL") or ""),
        token=env.get("GITHUB_TOKEN") or env.get("GIT_PROVIDER_USER_TOKEN") or None,
    )


def _github_provider(env: Mapping[str, str], api_url: str) -> GitProviderEnum:
    """GitHub or Gitea, told apart by the API they expose.

    Gitea Actions reuses GitHub's variable names, so the API root is the honest
    signal: Gitea serves it under `/api/v1`, GitHub Enterprise under `/api/v3`, and
    an explicit variable always wins over the guess.
    """
    for key in PROVIDER_OVERRIDES:
        override = (env.get(key) or "").strip().lower()
        if override in {item.value for item in GitProviderEnum}:
            return GitProviderEnum(override)

    if env.get("GITEA_ACTIONS") or api_url.rstrip("/").endswith(GITEA_API_SUFFIX):
        return GitProviderEnum.GITEA

    return GitProviderEnum.GITHUB


def _github_api_url(provider: GitProviderEnum, api_url: str, server_url: str) -> str | None:
    """The API root in the shape the port for this host builds its own paths on.

    Gitea's port appends `/api/v1` itself, so a Gitea API URL has to be reduced to
    the server root; GitHub's port appends nothing and takes the API URL as it is.
    """
    if provider is GitProviderEnum.GITHUB:
        return api_url or None

    root = api_url.rstrip("/")
    if root.endswith(GITEA_API_SUFFIX):
        root = root[: -len(GITEA_API_SUFFIX)]

    return root or server_url or None


def _read_event(path: str | None) -> dict:
    """The event payload GitHub leaves on disk, or an empty one."""
    if not path:
        return {}

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("could not read the CI event payload at %s: %s", path, exc)

        return {}

    return _as_mapping(payload)


def _as_mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""
