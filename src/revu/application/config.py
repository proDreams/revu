from logging import Logger

from dynaconf import Dynaconf, Validator

from revu.infrastructure.logger.project_logger import ProjectLogger


class Config:
    settings = Dynaconf(settings_files=["config/settings.yaml"], validators=[Validator("SYSTEM_PROMPT", default=None)])
    logger = ProjectLogger(settings=settings)


def get_settings() -> Dynaconf:
    return Config().settings


def get_logger(**kwargs) -> Logger:
    if not kwargs.get("name"):
        kwargs["name"] = __name__

    return Config.logger.get_logger(**kwargs)
