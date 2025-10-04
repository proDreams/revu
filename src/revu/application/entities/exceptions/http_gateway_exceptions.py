from revu.application.base.exception import CoreException


class HttpGatewayError(CoreException):
    pass


class HTTPGatewayAttemptLimitExceeded(HttpGatewayError):
    pass
