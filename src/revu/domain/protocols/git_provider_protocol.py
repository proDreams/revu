"""A git host that can both read a pull request and write into it.

This is the shape every host port has (GitHub, Gitea, GitLab, Bitbucket) and the
shape the webhook server needs. The two halves are declared separately — see
:mod:`git_reader_protocol` and :mod:`comment_publisher_protocol` — so that code
which only reads (the context builder) or only writes can say so, and so that a CI
run can pair a local reader with a host publisher.
"""

from typing import Protocol

from revu.domain.protocols.comment_publisher_protocol import CommentPublisherProtocol
from revu.domain.protocols.git_reader_protocol import GitReaderProtocol


class GitProviderProtocol(GitReaderProtocol, CommentPublisherProtocol, Protocol):
    """A host port: reads the change, publishes the review."""
