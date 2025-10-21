from logging import Logger

from dynaconf import Dynaconf, Validator

from revu.infrastructure.logger.project_logger import ProjectLogger


class Config:
    settings = Dynaconf(
        settings_files=["config/settings.yaml"],
        validators=[
            Validator("SYSTEM_PROMPT", default=None),
            Validator("LOG_DIR", default="logs"),
            Validator("LOG_FILE", default="logs.txt"),
            Validator("LOG_LEVEL", default="INFO"),
            Validator("MAX_SIZE_MB", default=10, cast=int),
            Validator("BACKUP_COUNT", default=5, cast=int),
            Validator("HTTP_CLIENT_TIMEOUT", default=30.0, cast=float),
            Validator("HTTP_CLIENT_REQUEST_ATTEMPTS", default=3, cast=int),
        ],
    )
    logger = ProjectLogger(settings=settings)


def get_settings() -> Dynaconf:
    return Config().settings


def get_logger(**kwargs) -> Logger:
    if not kwargs.get("name"):
        kwargs["name"] = __name__

    return Config.logger.get_logger(**kwargs)
