from revu.domain.entities.exceptions.base import CoreException


class HttpGatewayError(CoreException):
    pass


class HTTPGatewayAttemptLimitExceeded(HttpGatewayError):
    pass
