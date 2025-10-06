from revu.application.base.exception import CoreException


class UnknownGitProvider(CoreException):
    pass


class InvalidAIOutput(CoreException):
    pass
