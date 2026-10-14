from revu.domain.entities.exceptions.base import CoreException


class HttpGatewayError(CoreException):
    """An HTTP request that will not succeed by being repeated.

    Carries the status code when the server answered at all, so a caller can tell
    "this file is not there" (404) from "the host is unhappy with us" (403, 500)
    without parsing the message.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class HTTPGatewayAttemptLimitExceeded(HttpGatewayError):
    """Every attempt failed with something retryable."""
