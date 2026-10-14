import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from revu.application.config import LogSettings


class ProjectLogger:
    def __init__(self, settings: LogSettings):
        self.log_path = Path(settings.directory)
        self.log_file = self.log_path / settings.file
        self.log_level = settings.level
        self.max_log_size = settings.max_size_mb
        self.backup_count = settings.backup_count
        self.pre_registered_loggers = ["uvicorn", "httpx"]

        self._setup_logging_directory()

        for logger_name in self.pre_registered_loggers:
            self.get_logger(logger_name)

    def _setup_logging_directory(self):
        self.log_path.mkdir(parents=True, exist_ok=True)

    def _get_console_handler(self) -> logging.Handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(self.get_log_formatter())
        return console_handler

    def _get_file_handler(self) -> logging.Handler:
        file_handler = RotatingFileHandler(
            filename=self.log_file,
            encoding="utf-8",
            maxBytes=self.max_log_size * 1024 * 1024,
            backupCount=self.backup_count,
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(self.get_log_formatter())
        return file_handler

    @staticmethod
    def get_log_formatter() -> logging.Formatter:
        return logging.Formatter(
            fmt="[%(asctime)-25s][%(levelname)-8s][%(name)-35s]"
            "[%(filename)-20s][%(funcName)-25s][%(lineno)-5d][%(message)s]"
        )

    def get_logger(self, name: str | None = None) -> logging.Logger:
        logger = logging.getLogger(name)

        if not logger.hasHandlers():
            logger.setLevel(self.log_level)
            logger.addHandler(self._get_console_handler())
            logger.addHandler(self._get_file_handler())

        return logger
