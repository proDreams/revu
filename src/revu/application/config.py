"""Configuration loader.

Dynaconf stays the raw source (YAML file plus environment overrides), but every
consumer receives a frozen dataclass from
:mod:`revu.application.entities.config` instead of reading a global settings
object. Parsing and validation therefore live in exactly one place, produce
errors that name the offending key, and leave adapters constructible in tests
without patching globals.

Validation is intentionally not attached to Dynaconf: Dynaconf validates every
attached validator on any attribute access, which would make merely importing
the logger fail in an environment without a settings file (CI, for example).
"""

import logging
from collections.abc import Mapping
from logging import Logger
from typing import Any, NoReturn

from dynaconf import Dynaconf

from revu.application.entities.config import (
    CONNECTION_KEY_RE,
    DEFAULT_APP_HOST,
    DEFAULT_APP_PORT,
    DEFAULT_HTTP_ATTEMPTS,
    DEFAULT_HTTP_BACKOFF,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_INCLUDE_PR_DISCUSSION,
    DEFAULT_LOG_BACKUP_COUNT,
    DEFAULT_LOG_DIR,
    DEFAULT_LOG_FILE,
    DEFAULT_LOG_LEVEL,
    DEFAULT_LOG_MAX_SIZE_MB,
    DEFAULT_MAX_CONCURRENT_REVIEWS,
    DEFAULT_NOTIFY_ON_FAILURE,
    GIT_PROVIDERS_REQUIRING_URL,
    REQUIRED_AI_KEYS,
    SETTINGS_FILE,
    SUPPORTED_GIT_PROVIDERS,
    AIProfileConfig,
    AppSettings,
    ConfigError,
    GitConnectionConfig,
    HttpSettings,
    LogSettings,
    Settings,
)
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.enums.review_mode_enums import ReviewModeEnum
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.logger.project_logger import ProjectLogger


def _fail(message: str) -> NoReturn:
    raise ConfigError(message)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{path} must be a mapping of names to settings")

    return value


def _text(
    body: Mapping[str, Any],
    path: str,
    key: str,
    *,
    allowed: tuple[str, ...] | None = None,
    required: bool = True,
) -> str | None:
    value = body.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            _fail(f"{path}.{key} is required and must not be empty")

        return None

    text = str(value).strip()

    if allowed is not None and text not in allowed:
        _fail(f"{path}.{key} must be one of {', '.join(allowed)}; got {text!r}")

    return text


def _enum(
    body: Mapping[str, Any],
    path: str,
    key: str,
    enum_type: type,
    allowed: tuple[Any, ...],
    default: Any | None = None,
) -> Any:
    value = _text(body, path, key, allowed=tuple(item.value for item in allowed), required=default is None)
    if value is None:
        return default

    return enum_type(value)


def _positive_int(body: Mapping[str, Any], path: str, key: str, default: int) -> int:
    raw_value = body.get(key)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        _fail(f"{path}.{key} must be a positive integer; got {raw_value!r}")

    if value < 1:
        _fail(f"{path}.{key} must be a positive integer; got {value}")

    return value


TRUE_VALUES = frozenset({"true", "1", "yes", "on"})
FALSE_VALUES = frozenset({"false", "0", "no", "off"})


def _boolean(body: Mapping[str, Any], path: str, key: str, default: bool) -> bool:
    """Read a flag that may arrive as a YAML boolean or as a string."""
    raw_value = body.get(key)
    if raw_value is None:
        return default

    if isinstance(raw_value, bool):
        return raw_value

    text = str(raw_value).strip().lower()
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False

    _fail(f"{path}.{key} must be a boolean; got {raw_value!r}")


def _parse_ai_profiles(raw: Mapping[str, Any]) -> dict[str, AIProfileConfig]:
    section = raw.get("AI_PROVIDERS")
    if not section:
        _fail("AI_PROVIDERS must define at least one AI profile")

    profiles: dict[str, AIProfileConfig] = {}

    for name, body in _mapping(section, "AI_PROVIDERS").items():
        path = f"AI_PROVIDERS.{name}"
        body = _mapping(body, path)

        vendor = _enum(body, path, "AI_PROVIDER", AIProviderEnum, tuple(AIProviderEnum))

        for key in REQUIRED_AI_KEYS[vendor]:
            _text(body, path, key)

        profiles[str(name)] = AIProfileConfig(
            name=str(name),
            vendor=vendor,
            api_key=str(_text(body, path, "AI_PROVIDER_API_KEY")),
            model=str(_text(body, path, "AI_PROVIDER_MODEL")),
            base_url=_text(body, path, "AI_PROVIDER_BASE_URL", required=False),
            scope=_text(body, path, "AI_PROVIDER_SCOPE", required=False),
            folder_id=_text(body, path, "AI_PROVIDER_FOLDER_ID", required=False),
        )

    return profiles


def _parse_git_connections(
    raw: Mapping[str, Any],
    ai_profiles: Mapping[str, AIProfileConfig],
    default_ai_provider: str,
    default_review_mode: ReviewModeEnum,
    default_system_prompt: str | None,
    default_max_concurrent: int,
    default_notify_on_failure: bool,
    default_include_pr_discussion: bool,
) -> dict[str, GitConnectionConfig]:
    section = raw.get("GIT_PROVIDERS")
    if not section:
        _fail("GIT_PROVIDERS must define at least one git connection")

    known_profiles = ", ".join(sorted(ai_profiles))
    connections: dict[str, GitConnectionConfig] = {}

    for key, body in _mapping(section, "GIT_PROVIDERS").items():
        connection_key = str(key)
        path = f"GIT_PROVIDERS.{connection_key}"

        if not CONNECTION_KEY_RE.match(connection_key):
            _fail(
                f"{path} is not a valid connection key: it becomes the webhook URL, "
                f"so it must match {CONNECTION_KEY_RE.pattern}"
            )

        body = _mapping(body, path)

        host = _enum(body, path, "GIT_PROVIDER", GitProviderEnum, SUPPORTED_GIT_PROVIDERS)

        base_url = _text(body, path, "GIT_PROVIDER_URL", required=host in GIT_PROVIDERS_REQUIRING_URL)

        ai_provider = str(body.get("AI_PROVIDER") or default_ai_provider).strip()
        if ai_provider not in ai_profiles:
            _fail(
                f"{path}.AI_PROVIDER {ai_provider!r} is not defined in AI_PROVIDERS; known profiles: {known_profiles}"
            )

        connections[connection_key] = GitConnectionConfig(
            key=connection_key,
            host=host,
            user_token=str(_text(body, path, "GIT_PROVIDER_USER_TOKEN")),
            secret_token=str(_text(body, path, "GIT_PROVIDER_SECRET_TOKEN")),
            base_url=base_url,
            reviewer=_text(body, path, "GIT_PROVIDER_REVIEWER", required=False),
            ai_provider=ai_provider,
            review_mode=_enum(
                body,
                path,
                "REVIEW_MODE",
                ReviewModeEnum,
                tuple(ReviewModeEnum),
                default=default_review_mode,
            ),
            system_prompt=_text(body, path, "SYSTEM_PROMPT", required=False) or default_system_prompt,
            max_concurrent_reviews=_positive_int(body, path, "MAX_CONCURRENT_REVIEWS", default_max_concurrent),
            notify_on_failure=_boolean(body, path, "NOTIFY_ON_FAILURE", default_notify_on_failure),
            include_pr_discussion=_boolean(body, path, "INCLUDE_PR_DISCUSSION", default_include_pr_discussion),
        )

    return connections


def _load_settings(raw: Mapping[str, Any]) -> Settings:
    if raw.get("GIT_PROVIDER_CONFIG") is not None or raw.get("AI_PROVIDER_CONFIG") is not None:
        _fail(
            "the 1.x configuration format (GIT_PROVIDER_CONFIG / AI_PROVIDER_CONFIG) was removed in 2.0. "
            "Move those values into GIT_PROVIDERS and AI_PROVIDERS and set DEFAULT_AI_PROVIDER; "
            "see config/settings.yaml.example and CHANGELOG.md"
        )

    if not raw.get("GIT_PROVIDERS") and not raw.get("AI_PROVIDERS"):
        _fail(
            f"no provider configuration found: expected {SETTINGS_FILE} to define "
            "GIT_PROVIDERS, AI_PROVIDERS and DEFAULT_AI_PROVIDER "
            "(see config/settings.yaml.example)"
        )

    ai_profiles = _parse_ai_profiles(raw)
    default_ai_provider = str(_text(raw, "config", "DEFAULT_AI_PROVIDER"))

    if default_ai_provider not in ai_profiles:
        _fail(
            f"DEFAULT_AI_PROVIDER {default_ai_provider!r} is not defined in AI_PROVIDERS; "
            f"known profiles: {', '.join(sorted(ai_profiles))}"
        )

    review_mode = _enum(raw, "config", "REVIEW_MODE", ReviewModeEnum, tuple(ReviewModeEnum))

    git_connections = _parse_git_connections(
        raw,
        ai_profiles=ai_profiles,
        default_ai_provider=default_ai_provider,
        default_review_mode=review_mode,
        default_system_prompt=_text(raw, "config", "SYSTEM_PROMPT", required=False),
        default_max_concurrent=int(raw.get("MAX_CONCURRENT_REVIEWS") or DEFAULT_MAX_CONCURRENT_REVIEWS),
        default_notify_on_failure=_boolean(raw, "config", "NOTIFY_ON_FAILURE", DEFAULT_NOTIFY_ON_FAILURE),
        default_include_pr_discussion=_boolean(raw, "config", "INCLUDE_PR_DISCUSSION", DEFAULT_INCLUDE_PR_DISCUSSION),
    )

    return Settings(
        git_connections=git_connections,
        ai_profiles=ai_profiles,
        default_ai_provider=default_ai_provider,
        http=HttpSettings(
            timeout=float(raw.get("HTTP_CLIENT_TIMEOUT") or DEFAULT_HTTP_TIMEOUT),
            attempts=int(raw.get("HTTP_CLIENT_REQUEST_ATTEMPTS") or DEFAULT_HTTP_ATTEMPTS),
            backoff=float(raw.get("HTTP_CLIENT_RETRY_BACKOFF") or DEFAULT_HTTP_BACKOFF),
        ),
        log=load_log_settings(raw),
        app=AppSettings(
            host=str(raw.get("APP_HOST") or DEFAULT_APP_HOST),
            port=int(raw.get("APP_PORT") or DEFAULT_APP_PORT),
        ),
    )


class Config:
    """Raw settings source. Use :func:`load_settings` for the typed view."""

    settings = Dynaconf(settings_files=[SETTINGS_FILE])

    _project_logger: ProjectLogger | None = None

    @classmethod
    def get_project_logger(cls) -> ProjectLogger:
        """Build the console/file logger on first use.

        It reads only keys that have defaults, so importing the configuration
        module never requires a settings file to exist.
        """
        if cls._project_logger is None:
            cls._project_logger = ProjectLogger(settings=load_log_settings())

        return cls._project_logger


def load_settings(raw: Mapping[str, Any] | None = None) -> Settings:
    """Parse and validate the configuration, or raise :class:`ConfigError`.

    Pass ``raw`` explicitly in tests; production passes nothing and the Dynaconf
    settings file (plus environment overrides) is used.
    """
    settings = _load_settings(Config.settings if raw is None else raw)
    _warn_about_duplicate_connections(settings)

    return settings


def load_log_settings(raw: Mapping[str, Any] | None = None) -> LogSettings:
    """Read the logging keys only, with defaults, for the logger bootstrap."""
    source = Config.settings if raw is None else raw

    return LogSettings(
        directory=str(source.get("LOG_DIR") or DEFAULT_LOG_DIR),
        file=str(source.get("LOG_FILE") or DEFAULT_LOG_FILE),
        level=str(source.get("LOG_LEVEL") or DEFAULT_LOG_LEVEL),
        max_size_mb=int(source.get("MAX_SIZE_MB") or DEFAULT_LOG_MAX_SIZE_MB),
        backup_count=int(source.get("BACKUP_COUNT") or DEFAULT_LOG_BACKUP_COUNT),
    )


def _warn_about_duplicate_connections(settings: Settings) -> None:
    """Two connections to the same host and URL risk reviewing a PR twice."""
    seen: dict[tuple[GitProviderEnum, str | None], str] = {}

    for connection in settings.git_connections.values():
        identity = (connection.host, connection.base_url)
        previous = seen.get(identity)

        if previous is not None:
            logging.getLogger(__name__).warning(
                "git connections %r and %r use the same host and base URL; "
                "a repository reachable through both will be reviewed twice",
                previous,
                connection.key,
            )

        seen[identity] = connection.key


def get_logger(**kwargs) -> Logger:
    if not kwargs.get("name"):
        kwargs["name"] = __name__

    return Config.get_project_logger().get_logger(**kwargs)
