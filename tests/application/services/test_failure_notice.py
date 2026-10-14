"""The message published when a review fails must be useful and leak-free."""

import pytest

from revu.application.entities.exceptions.ai_adapters_exceptions import (
    InvalidAIOutput,
    NoAIResponse,
)
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HTTPGatewayAttemptLimitExceeded,
    HttpGatewayError,
)
from revu.application.entities.exceptions.review_service_exceptions import (
    ReviewModeException,
)
from revu.application.services.failure_notice import failure_hint, failure_notice
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (InvalidAIOutput("raw model output"), "не удалось разобрать"),
        (NoAIResponse("empty"), "пустой ответ"),
        (HTTPGatewayAttemptLimitExceeded("limit"), "исчерпаны попытки"),
        (HttpGatewayError("HTTP 401 from ..."), "ответил ошибкой"),
        (UnsupportedReviewCommentException("foreign"), "не подходит выбранному Git-провайдеру"),
        (ReviewModeException("bogus"), "неизвестный REVIEW_MODE"),
        (RuntimeError("boom"), "внутренняя ошибка сервиса"),
    ],
)
def test_a_hint_matches_the_failure(exc, expected):
    assert expected in failure_hint(exc)


def test_a_subclass_is_matched_before_its_base_class():
    """HTTPGatewayAttemptLimitExceeded extends HttpGatewayError."""
    assert "исчерпаны попытки" in failure_hint(HTTPGatewayAttemptLimitExceeded("x"))


def test_the_notice_names_the_error_type_but_not_its_message():
    notice = failure_notice(InvalidAIOutput("secret model output: sk-123"))

    assert "ReVu не смог выполнить ревью" in notice
    assert "InvalidAIOutput" in notice
    assert "sk-123" not in notice


def test_the_notice_points_at_the_logs():
    assert "логи сервиса" in failure_notice(RuntimeError("boom"))
