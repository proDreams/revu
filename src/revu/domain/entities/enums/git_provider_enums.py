from enum import StrEnum


class GitProviderEnum(StrEnum):
    """Git hosts ReVu can talk to.

    Only implemented hosts are listed: the configuration validator rejects
    anything else, so a port never receives an unsupported host.
    """

    GITHUB = "github"
    GITEA = "gitea"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
