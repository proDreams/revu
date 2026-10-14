from enum import StrEnum


class PullRequestActionEnum(StrEnum):
    """Actions ReVu reacts to.

    ``synchronize`` is what GitHub sends for new commits, ``synchronized``
    is Gitea's spelling of the same event.
    """

    OPENED = "opened"
    REOPENED = "reopened"
    SYNCHRONIZE = "synchronize"
    SYNCHRONIZED = "synchronized"

    @classmethod
    def is_review_trigger(cls, value: str) -> bool:
        """Return True when the action should start an AI review."""
        try:
            cls(value)
        except ValueError:
            return False

        return True
