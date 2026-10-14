from logging import Logger

from dynaconf import Dynaconf, Validator
from dynaconf.validator import ValidatorList

from revu.infrastructure.logger.project_logger import ProjectLogger

GIT_PROVIDERS = ["github", "gitea", "bitbucket"]
AI_PROVIDERS = ["openai", "openai_compatible", "gigachat", "yandexgpt"]
REVIEW_MODES = ["comment", "inline"]

# Keys with a safe fallback. They stay attached to the settings object because
# Dynaconf applies `default` lazily on attribute access, which is what the
# logger, the HTTP gateway and the feature guards rely on.
DEFAULTED_VALIDATORS = [
    Validator("SYSTEM_PROMPT", default=None),
    Validator("LOG_DIR", default="logs"),
    Validator("LOG_FILE", default="logs.txt"),
    Validator("LOG_LEVEL", default="INFO"),
    Validator("MAX_SIZE_MB", default=10, cast=int),
    Validator("BACKUP_COUNT", default=5, cast=int),
    Validator("HTTP_CLIENT_TIMEOUT", default=30.0, cast=float),
    Validator("HTTP_CLIENT_REQUEST_ATTEMPTS", default=3, cast=int),
    Validator("HTTP_CLIENT_RETRY_BACKOFF", default=0.5, cast=float),
    Validator("MAX_CONCURRENT_REVIEWS", default=3, cast=int),
    Validator("APP_HOST", default="0.0.0.0"),
    Validator("APP_PORT", default=8000, cast=int),
]

# Keys the service cannot work without. They are deliberately *not* attached to
# the settings object: Dynaconf validates every attached validator on any
# attribute access, so a strict validator there would make merely importing the
# logger blow up in an environment without a settings file (CI, for instance).
# They run explicitly from validate_settings() at startup instead.
REQUIRED_VALIDATORS = [
    Validator("REVIEW_MODE", must_exist=True, is_in=REVIEW_MODES),
    Validator("GIT_PROVIDER_CONFIG.GIT_PROVIDER", must_exist=True, is_in=GIT_PROVIDERS),
    Validator("GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN", must_exist=True, ne=""),
    # An empty secret would make every webhook signature forgeable.
    Validator("GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN", must_exist=True, ne=""),
    # GitHub is addressed through api.github.com unless a base URL is given, so
    # only the two hosts that are always self-hosted require one.
    Validator(
        "GIT_PROVIDER_CONFIG.GIT_PROVIDER_URL",
        must_exist=True,
        when=Validator("GIT_PROVIDER_CONFIG.GIT_PROVIDER", is_in=["gitea", "bitbucket"]),
    ),
    Validator("GIT_PROVIDER_CONFIG.GIT_PROVIDER_REVIEWER", default=None),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER", must_exist=True, is_in=AI_PROVIDERS),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER_API_KEY", must_exist=True, ne=""),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER_MODEL", must_exist=True, ne=""),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER_BASE_URL", default=None),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER_SCOPE", default=None),
    Validator("AI_PROVIDER_CONFIG.AI_PROVIDER_FOLDER_ID", default=None),
]


class Config:
    settings = Dynaconf(
        settings_files=["config/settings.yaml"],
        validators=DEFAULTED_VALIDATORS,
    )

    _project_logger: ProjectLogger | None = None

    @classmethod
    def get_project_logger(cls) -> ProjectLogger:
        """Build the console/file logger on first use.

        Creating it at import time made importing the configuration module
        create a log directory and open a file handler as a side effect.
        """
        if cls._project_logger is None:
            cls._project_logger = ProjectLogger(settings=cls.settings)

        return cls._project_logger


def get_settings() -> Dynaconf:
    return Config.settings


def validate_settings() -> None:
    """Fail fast on a configuration the service cannot work with.

    Called once while the application starts, so a typo in ``REVIEW_MODE`` or a
    missing provider token is reported immediately instead of turning every
    webhook into a silently swallowed background failure.
    """
    ValidatorList(Config.settings, validators=REQUIRED_VALIDATORS).validate()


def get_logger(**kwargs) -> Logger:
    if not kwargs.get("name"):
        kwargs["name"] = __name__

    return Config.get_project_logger().get_logger(**kwargs)
