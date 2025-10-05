from enum import StrEnum


class PullRequestActionEnum(StrEnum):
    OPENED = "opened"
    REOPENED = "reopened"
    SYNCHRONIZE = "synchronize"
