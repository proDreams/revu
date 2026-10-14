import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from revu.application.config import LogSettings
from revu.infrastructure.logger.connection_context import (
    UNKNOWN_CONNECTION,
    ConnectionKeyFilter,
)


class _LazyFileHandler(logging.Handler):
    """Creates the log file when the first record is emitted, not before.

    Importing the application imports the configuration module, which builds the
    logger; creating ``logs/`` and opening a file as a side effect of an import
    surprised tests and CLI tools that never log anything.
    """

    def __init__(self, settings: LogSettings) -> None:
        super().__init__()
        self._settings = settings
        self._delegate: logging.Handler | None = None

    def emit(self, record: logging.LogRecord) -> None:
        self._get_delegate().emit(record)

    def _get_delegate(self) -> logging.Handler:
        if self._delegate is None:
            self._delegate = self._build()
            self._delegate.setLevel(self.level)
            self._delegate.setFormatter(self.formatter)

        return self._delegate

    def _build(self) -> logging.Handler:
        log_path = Path(self._settings.directory)
        log_path.mkdir(parents=True, exist_ok=True)

        return RotatingFileHandler(
            filename=log_path / self._settings.file,
            encoding="utf-8",
            maxBytes=self._settings.max_size_mb * 1024 * 1024,
            backupCount=self._settings.backup_count,
        )

    def close(self) -> None:
        if self._delegate is not None:
            self._delegate.close()

        super().close()


class ProjectLogger:
    def __init__(self, settings: LogSettings):
        self.settings = settings
        self.log_path = Path(settings.directory)
        self.log_file = self.log_path / settings.file
        self.log_level = settings.level
        self.pre_registered_loggers = ["uvicorn", "httpx"]

        for logger_name in self.pre_registered_loggers:
            self.get_logger(logger_name)

    def _get_console_handler(self) -> logging.Handler:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(self.get_log_formatter())
        console_handler.addFilter(ConnectionKeyFilter())

        return console_handler

    def _get_file_handler(self) -> logging.Handler:
        file_handler = _LazyFileHandler(self.settings)
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(self.get_log_formatter())
        file_handler.addFilter(ConnectionKeyFilter())

        return file_handler

    @staticmethod
    def get_log_formatter() -> logging.Formatter:
        # `defaults` keeps the formatter usable on a record that never passed
        # through the filter (a bare LogRecord formatted in a test, for example).
        return logging.Formatter(
            fmt="[%(asctime)-25s][%(levelname)-8s][%(connection_key)-16s][%(name)-35s]"
            "[%(filename)-20s][%(funcName)-25s][%(lineno)-5d][%(message)s]",
            defaults={"connection_key": UNKNOWN_CONNECTION},
        )

    def get_logger(self, name: str | None = None) -> logging.Logger:
        logger = logging.getLogger(name)

        if not logger.hasHandlers():
            logger.setLevel(self.log_level)
            logger.addHandler(self._get_console_handler())
            logger.addHandler(self._get_file_handler())

        return logger
