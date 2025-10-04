from enum import StrEnum


class PullRequestActionEnum(StrEnum):
    OPENED = "opened"
    REOPENED = "reopened"
    SYNCHRONIZE = "synchronize"


class GitProviderEnum(StrEnum):
    GITHUB = "github"
    GITLAB = "gitlab"
    GITEA = "gitea"
    BITBUCKET = "bitbucket"


class AIProviderEnum(StrEnum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai_compatible"
