"""Remembers which revision of a pull request was last reviewed.

GitLab fires its ``update`` action for a renamed title or a new label as well as
for a push, and its payload has no field that separates the two
(gitlab-org/gitlab#10824). The head commit is therefore the only reliable signal,
and telling the two apart needs a little memory.
"""

from collections import OrderedDict

DEFAULT_REVISION_CAPACITY = 1024


class ReviewedRevisionStore:
    """A bounded record of the reviewed head commit per pull request."""

    def __init__(self, capacity: int = DEFAULT_REVISION_CAPACITY) -> None:
        self._capacity = capacity
        self._revisions: OrderedDict[tuple[str, str, int], str] = OrderedDict()

    def has_reviewed(self, connection_key: str, repo: str, index: int, revision: str) -> bool:
        return self._revisions.get((connection_key, repo, index)) == revision

    def remember(self, connection_key: str, repo: str, index: int, revision: str) -> None:
        """Record a revision, evicting the least recently used one when full.

        Eviction costs at most one redundant review later; forgetting a revision
        can never lose one.
        """
        key = (connection_key, repo, index)

        self._revisions[key] = revision
        self._revisions.move_to_end(key)

        while len(self._revisions) > self._capacity:
            self._revisions.popitem(last=False)
