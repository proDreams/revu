import logging

from revu.infrastructure.logger.project_logger import ProjectLogger


def _cleanup_logger(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_project_logger_creates_handlers(settings, tmp_path):
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    project_logger = ProjectLogger(settings=settings)
    logger = project_logger.get_logger("app.test")

    try:
        logger.info("test message")
        assert len(logger.handlers) == 2
        assert any(isinstance(handler, logging.StreamHandler) for handler in logger.handlers)
        assert project_logger.log_path.exists()
        assert (project_logger.log_path / settings.LOG_FILE).exists()
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
