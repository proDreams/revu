from typing import Annotated

from pydantic import BaseModel, StringConstraints

from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum


class Repo(BaseModel):
    full_name: str


class Branch(BaseModel):
    sha: Annotated[str, StringConstraints(min_length=40, max_length=40)]


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
