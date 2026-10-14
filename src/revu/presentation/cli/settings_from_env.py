"""Building one run's configuration out of the environment.

The same parser and the same keys as `settings.yaml` do the work, so a value that is
valid in a file is valid here and the validation is identical: a mistyped review
mode fails the job with the message it would have failed the server with.

What differs is the shape. A file describes a server — many connections, each with
its own webhook URL and secret. A pipeline reviews one change in one repository, so
that map is built here, with a single entry, from variables a user already knows
from the file.
"""

from collections.abc import Mapping

from revu.application.config import load_settings
from revu.application.entities.config import DEFAULT_REVIEW_MODE, Settings
from revu.presentation.cli.environment import CiEnvironment

#: The single connection and AI profile a pipeline run needs. The connection key is
#: the same shape a webhook URL would use, because the same validator reads it.
CONNECTION_KEY = "ci-run"
PROFILE_KEY = "ci-run"

#: A webhook secret exists to verify an inbound event; a pipeline is the author of
#: its own event, so nothing ever checks it. The parser still requires one.
UNUSED_WEBHOOK_SECRET = "not-used-in-ci"

#: A token stands in for the connection's own when a run never calls the host — a
#: checkout and a job log need nobody to authenticate as. The command refuses to
#: reach this point with an API to call and no token (see :func:`._require_token`),
#: so the placeholder cannot end up in a request.
UNUSED_TOKEN = "not-used-in-ci"

#: AI vendor used when the environment does not name one.
DEFAULT_AI_VENDOR = "openai"

#: Read from the environment and passed through untouched, exactly as they would be
#: written in `settings.yaml`.
PASSTHROUGH_KEYS = (
    "REVIEW_MODE",
    "SYSTEM_PROMPT",
    "CONTEXT_DEPTH",
    "CONTEXT_MAX_FILES",
    "CONTEXT_MAX_CHARS",
    "INCLUDE_PR_DISCUSSION",
    "NOTIFY_ON_FAILURE",
    "HTTP_CLIENT_TIMEOUT",
    "HTTP_CLIENT_REQUEST_ATTEMPTS",
    "HTTP_CLIENT_RETRY_BACKOFF",
    "LOG_LEVEL",
)

#: Keys of an AI profile, shared by every vendor.
AI_PROFILE_KEYS = (
    "AI_PROVIDER_API_KEY",
    "AI_PROVIDER_MODEL",
    "AI_PROVIDER_BASE_URL",
    "AI_PROVIDER_SCOPE",
    "AI_PROVIDER_FOLDER_ID",
)


def build_settings(environment: CiEnvironment, env: Mapping[str, str]) -> Settings:
    """A validated :class:`Settings` for this run."""
    connection: dict[str, object] = {
        "GIT_PROVIDER": environment.provider.value,
        "GIT_PROVIDER_USER_TOKEN": env.get("GIT_PROVIDER_USER_TOKEN") or environment.token or UNUSED_TOKEN,
        "GIT_PROVIDER_SECRET_TOKEN": UNUSED_WEBHOOK_SECRET,
        "AI_PROVIDER": PROFILE_KEY,
    }

    api_url = env.get("GIT_PROVIDER_URL") or environment.api_url
    if api_url:
        connection["GIT_PROVIDER_URL"] = api_url

    profile: dict[str, object] = {"AI_PROVIDER": (env.get("AI_PROVIDER") or DEFAULT_AI_VENDOR).strip()}
    profile.update({key: env[key] for key in AI_PROFILE_KEYS if env.get(key)})

    raw: dict[str, object] = {
        "GIT_PROVIDERS": {CONNECTION_KEY: connection},
        "AI_PROVIDERS": {PROFILE_KEY: profile},
        "DEFAULT_AI_PROVIDER": PROFILE_KEY,
        # The file always states a review mode; a pipeline that says nothing gets
        # the same answer ReVu gives by default rather than a configuration error.
        "REVIEW_MODE": env.get("REVIEW_MODE") or DEFAULT_REVIEW_MODE.value,
    }
    raw.update({key: env[key] for key in PASSTHROUGH_KEYS if env.get(key)})

    return load_settings(raw)
