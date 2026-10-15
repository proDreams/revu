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
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnsupportedReviewCommentException,
)

DEFAULT_HINT = "внутренняя ошибка сервиса"

#: How a failed review is retried is the one thing that differs by where ReVu runs:
#: a server waits for another webhook, a pipeline is restarted.
SERVER_RETRY_HINT = "Ревью можно перезапустить, отправив вебхук повторно."

#: What each host documents about a token's access, taken from its API documentation
#: rather than inferred. Every supported host hides a repository the token's user may
#: not read — it answers 404, exactly like a URL with a typo — so a refusal and a wrong
#: address look the same without knowing what the host requires. Gitea groups token
#: scopes by API route (`/repos/*` for diffs and files, `issues/*` for comments) and
#: states that a scope is required even for a public repository, so a token created
#: without scopes sees nothing at all.
ACCESS_HINTS: dict[GitProviderEnum, str] = {
    GitProviderEnum.GITEA: (
        "Gitea: области токена задаются по группам маршрутов — `read:repository` для диффов, файлов и PR, "
        "`write:issue` для комментариев; область обязательна даже для публичного репозитория, "
        "а репозиторий, недоступный пользователю токена, отвечает 404"
    ),
    GitProviderEnum.GITHUB: (
        "GitHub: токену нужна область `repo`; репозиторий, недоступный пользователю токена, отвечает 404"
    ),
    GitProviderEnum.GITLAB: (
        "GitLab: токену нужна область `api` — и для чтения диффа, и для комментариев; "
        "проект, недоступный пользователю токена, отвечает 404"
    ),
    GitProviderEnum.BITBUCKET: (
        "Bitbucket: токену нужны права на чтение репозитория и на запись комментариев; "
        "недоступный репозиторий отвечает 404"
    ),
}

#: Statuses that mean "the host will not show this to you" rather than "the host is
#: broken": a token that is missing, wrong, short of a scope, or without access.
ACCESS_STATUSES = frozenset({401, 403, 404})

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


def failure_notice(exc: BaseException, retry_hint: str = SERVER_RETRY_HINT) -> str:
    """Build the comment published on the pull request after a failed review."""
    return (
        "⚠️ **ReVu не смог выполнить ревью.**\n\n"
        f"Причина: {failure_hint(exc)} (`{type(exc).__name__}`).\n\n"
        f"Подробности — в логах. {retry_hint}"
    )


def access_hint(host: GitProviderEnum, exc: BaseException) -> str | None:
    """What the host documents about a refusal, or ``None`` when it is not one.

    This belongs in the log and not in the pull request: a token's scopes are the
    operator's business, while the author only needs to know that the review failed.
    """
    if not isinstance(exc, HttpGatewayError) or exc.status_code not in ACCESS_STATUSES:
        return None

    return ACCESS_HINTS.get(host)
