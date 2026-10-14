from revu.domain.entities.exceptions.base import CoreException


class UnknownGitProviderException(CoreException):
    """The configured or requested git provider is not supported."""


class UnsupportedReviewCommentException(CoreException):
    """A review comment cannot be published through the current git provider.

    Raised when the AI produced comment objects for a different host than the
    one ReVu is configured with, for example GitHub comments on a Bitbucket
    setup.
    """
