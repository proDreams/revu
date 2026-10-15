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
from revu.application.services.failure_notice import (
    access_hint,
    failure_hint,
    failure_notice,
)
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
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
    assert "Подробности — в логах" in failure_notice(RuntimeError("boom"))


def test_the_retry_advice_differs_by_where_revu_runs():
    """A server waits for another webhook; a pipeline is restarted."""
    assert "вебхук повторно" in failure_notice(RuntimeError("boom"))
    assert "перезапустив job" in failure_notice(
        RuntimeError("boom"), retry_hint="Ревью можно перезапустить, перезапустив job."
    )


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        # The scopes below are quoted from each host's own API documentation.
        (GitProviderEnum.GITEA, "read:repository"),
        (GitProviderEnum.GITEA, "write:issue"),
        (GitProviderEnum.GITHUB, "`repo`"),
        (GitProviderEnum.GITLAB, "`api`"),
        (GitProviderEnum.BITBUCKET, "права"),
    ],
)
def test_a_refusal_names_what_the_host_requires(host, expected):
    hint = access_hint(host, HttpGatewayError("HTTP 404", status_code=404))

    assert hint is not None
    assert expected in hint


@pytest.mark.parametrize("status", [401, 403, 404])
def test_every_refusal_counts_as_an_access_problem(status):
    """A missing token, a wrong token, a missing scope and no access all hide as these."""
    assert access_hint(GitProviderEnum.GITEA, HttpGatewayError("HTTP", status_code=status)) is not None


@pytest.mark.parametrize("status", [500, 502, 429])
def test_a_host_that_is_merely_unwell_is_not_described_as_a_token_problem(status):
    assert access_hint(GitProviderEnum.GITEA, HttpGatewayError("HTTP", status_code=status)) is None


def test_an_error_that_is_not_from_a_host_gets_no_access_hint():
    assert access_hint(GitProviderEnum.GITEA, RuntimeError("boom")) is None


def test_a_gateway_error_without_a_status_gets_no_access_hint():
    """The attempt limit subclasses the gateway error and carries no status."""
    assert access_hint(GitProviderEnum.GITEA, HTTPGatewayAttemptLimitExceeded("no more attempts")) is None


def test_the_pull_request_notice_stays_free_of_operator_details():
    """Scopes are the operator's business; the author is told only that it failed."""
    notice = failure_notice(HttpGatewayError("HTTP 404", status_code=404))

    assert "read:repository" not in notice
    assert "области токена" not in notice
