"""Typed configuration model.

Kept apart from the loader (:mod:`revu.application.config`) so that
infrastructure pieces such as the logger can depend on the model without
importing Dynaconf or creating an import cycle.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.enums.webhook_service_enums import ReviewModeEnum
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.base import CoreException

SETTINGS_FILE = "config/settings.yaml"

# Only the hosts ReVu actually implements; GitProviderEnum also lists gitlab,
# which has no port yet.
SUPPORTED_GIT_PROVIDERS = (
    GitProviderEnum.GITHUB,
    GitProviderEnum.GITEA,
    GitProviderEnum.BITBUCKET,
)

# Mandatory keys per AI vendor. Everything else is optional.
REQUIRED_AI_KEYS: dict[AIProviderEnum, tuple[str, ...]] = {
    AIProviderEnum.OPENAI: ("AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL"),
    AIProviderEnum.OPENAI_COMPATIBLE: ("AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "AI_PROVIDER_BASE_URL"),
    AIProviderEnum.GIGACHAT: ("AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL"),
    AIProviderEnum.YANDEXGPT: ("AI_PROVIDER_API_KEY", "AI_PROVIDER_MODEL", "AI_PROVIDER_FOLDER_ID"),
}

# Connections that are always self-hosted need an explicit base URL; github.com
# has a default and only uses one for GitHub Enterprise.
GIT_PROVIDERS_REQUIRING_URL = (GitProviderEnum.GITEA, GitProviderEnum.BITBUCKET)

# The key becomes a path segment of the webhook URL, so keep it URL-safe.
CONNECTION_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")

DEFAULT_REVIEW_MODE = ReviewModeEnum.INLINE
DEFAULT_MAX_CONCURRENT_REVIEWS = 3
DEFAULT_HTTP_TIMEOUT = 30.0
DEFAULT_HTTP_ATTEMPTS = 3
DEFAULT_HTTP_BACKOFF = 0.5
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "logs.txt"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_MAX_SIZE_MB = 10
DEFAULT_LOG_BACKUP_COUNT = 5
DEFAULT_APP_HOST = "0.0.0.0"
DEFAULT_APP_PORT = 8000


class ConfigError(CoreException):
    """The configuration cannot be used; raised while the application starts."""


class UnknownConnectionError(CoreException):
    """A webhook arrived for a connection key that is not configured."""


@dataclass(frozen=True, slots=True)
class HttpSettings:
    timeout: float
    attempts: int
    backoff: float


@dataclass(frozen=True, slots=True)
class LogSettings:
    directory: str
    file: str
    level: str
    max_size_mb: int
    backup_count: int


@dataclass(frozen=True, slots=True)
class AppSettings:
    host: str
    port: int


@dataclass(frozen=True, slots=True)
class AIProfileConfig:
    """A named set of AI provider settings, shareable by many connections."""

    name: str
    vendor: AIProviderEnum
    api_key: str
    model: str
    base_url: str | None = None
    scope: str | None = None
    folder_id: str | None = None


@dataclass(frozen=True, slots=True)
class GitConnectionConfig:
    """One git host credential set, addressed by ``key`` in the webhook URL."""

    key: str
    host: GitProviderEnum
    user_token: str
    secret_token: str
    ai_provider: str
    review_mode: ReviewModeEnum
    max_concurrent_reviews: int
    base_url: str | None = None
    reviewer: str | None = None
    system_prompt: str | None = None

    @property
    def resolved_base_url(self) -> str:
        """The base URL, guaranteed to exist for hosts that require one."""
        if not self.base_url:
            raise ConfigError(f"GIT_PROVIDERS.{self.key}.GIT_PROVIDER_URL is required for {self.host.value}")

        return self.base_url


@dataclass(frozen=True, slots=True)
class Settings:
    git_connections: Mapping[str, GitConnectionConfig]
    ai_profiles: Mapping[str, AIProfileConfig]
    default_ai_provider: str
    http: HttpSettings
    log: LogSettings
    app: AppSettings

    def ai_profile_for(self, connection: GitConnectionConfig) -> AIProfileConfig:
        """Resolve the AI profile of a connection (explicit or default)."""
        return self.ai_profiles[connection.ai_provider]
