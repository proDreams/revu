from revu.domain.entities.exceptions.base import CoreException


class UnknownGitProvider(CoreException):
    pass


class InvalidAIOutput(CoreException):
    pass


class NoAIResponse(CoreException):
    pass
