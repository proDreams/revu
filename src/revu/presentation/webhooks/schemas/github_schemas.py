from pydantic import BaseModel

from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum


class Repo(BaseModel):
    full_name: str


class Branch(BaseModel):
    sha: str


class PullRequest(BaseModel):
    number: int
    head: Branch
    title: str
    body: str | None = None


class GithubPullRequestWebhook(BaseModel):
    action: PullRequestActionEnum
    pull_request: PullRequest
    repository: Repo


class GiteaPullRequestWebhook(GithubPullRequestWebhook):
    pass


class GitVersePullRequestWebhook(GithubPullRequestWebhook):
    pass
