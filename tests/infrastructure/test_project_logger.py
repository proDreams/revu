import logging

import pytest

from revu.application.config import get_logger
from revu.application.entities.config import LogSettings
from revu.infrastructure.logger.connection_context import (
    reset_connection_key,
    set_connection_key,
)
from revu.infrastructure.logger.project_logger import ProjectLogger

pytestmark = pytest.mark.unit


def _cleanup_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_project_logger_creates_handlers(log_settings, tmp_path):
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    project_logger = ProjectLogger(settings=log_settings)
    logger = project_logger.get_logger("app.test")

    try:
        logger.info("test message")
        assert len(logger.handlers) == 2
        assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
        assert project_logger.log_path.exists()
        assert (project_logger.log_path / log_settings.file).exists()
    finally:
        _cleanup_logger(logger)
        pref_logger = logging.getLogger("pref")
        _cleanup_logger(pref_logger)


def test_project_logger_formatter_contains_expected_fields():
    formatter = ProjectLogger.get_log_formatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=10,
        msg="hello",
        args=(),
        exc_info=None,
    )
    formatted = formatter.format(record)
    assert "[test" in formatted
    assert "hello" in formatted


def test_get_logger_returns_logger():
    logger = get_logger(name=__name__)

    assert isinstance(logger, logging.Logger)
    assert logger.name == __name__


def test_get_logger_without_name():
    logger = get_logger()

    assert isinstance(logger, logging.Logger)
    assert logger.name == "revu.application.config"


def _clear_root_handlers() -> None:
    """pytest attaches a handler to the root logger, which makes hasHandlers()
    true for every logger and would stop ProjectLogger from adding its own."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()


def test_the_log_directory_is_not_created_before_the_first_record(tmp_path):
    """Importing the application builds the logger; that must not touch the disk."""
    _clear_root_handlers()

    project_logger = ProjectLogger(
        settings=LogSettings(
            directory=str(tmp_path / "not-yet"),
            file="logs.txt",
            level="DEBUG",
            max_size_mb=1,
            backup_count=1,
        )
    )

    assert not project_logger.log_path.exists()

    logger = project_logger.get_logger("lazy.test")
    try:
        logger.info("first record")
        assert (project_logger.log_path / "logs.txt").exists()
    finally:
        _cleanup_logger(logger)


def test_every_record_carries_the_connection_key(tmp_path):
    _clear_root_handlers()

    project_logger = ProjectLogger(
        settings=LogSettings(
            directory=str(tmp_path),
            file="logs.txt",
            level="DEBUG",
            max_size_mb=1,
            backup_count=1,
        )
    )
    logger = project_logger.get_logger("context.test")

    token = set_connection_key("gh-main")
    try:
        formatter = project_logger.get_log_formatter()
        record = logging.LogRecord(
            name="context.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        # The filter is what attaches the key.
        project_logger._get_console_handler().filter(record)
        assert "gh-main" in formatter.format(record)
    finally:
        reset_connection_key(token)
        _cleanup_logger(logger)


def test_the_formatter_works_on_a_record_that_never_saw_the_filter():
    formatter = ProjectLogger.get_log_formatter()
    record = logging.LogRecord(
        name="bare",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )

    assert "hello" in formatter.format(record)
