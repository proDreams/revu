"""The comment published when a review could not be completed.

Only the exception *type* reaches the pull request: the full message can carry
provider responses (and, from some SDKs, request details), while the log already
holds the traceback for the operator.
"""

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
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)

DEFAULT_HINT = "внутренняя ошибка сервиса"

# Most specific first: subclasses are matched before their base classes.
FAILURE_HINTS: tuple[tuple[type[Exception], str], ...] = (
    (InvalidAIOutput, "ИИ-провайдер вернул ответ, который не удалось разобрать"),
    (NoAIResponse, "ИИ-провайдер вернул пустой ответ"),
    (HTTPGatewayAttemptLimitExceeded, "не удалось обратиться к Git- или ИИ-провайдеру: исчерпаны попытки"),
    (HttpGatewayError, "Git- или ИИ-провайдер ответил ошибкой"),
    (UnsupportedReviewCommentException, "формат комментариев не подходит выбранному Git-провайдеру"),
    (ReviewModeException, "в конфигурации указан неизвестный REVIEW_MODE"),
)


def failure_hint(exc: BaseException) -> str:
    for exception_type, hint in FAILURE_HINTS:
        if isinstance(exc, exception_type):
            return hint

    return DEFAULT_HINT


def failure_notice(exc: BaseException) -> str:
    """Build the comment published on the pull request after a failed review."""
    return (
        "⚠️ **ReVu не смог выполнить ревью.**\n\n"
        f"Причина: {failure_hint(exc)} (`{type(exc).__name__}`).\n\n"
        "Проверьте логи сервиса — там подробности. Ревью можно перезапустить, "
        "отправив вебхук повторно."
    )
