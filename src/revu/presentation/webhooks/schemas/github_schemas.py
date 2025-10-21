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


class BitBucketPullRequestWebhook(GithubPullRequestWebhook):
    pass


class _BBPR(BaseModel):
    key: str


class _BBRP(BaseModel):
    slug: str
    project: _BBPR


class _BBTR(BaseModel):
    latestCommit: str
    repository: _BBRP


class _BBPlR(BaseModel):
    id: int
    title: str
    toRef: _BBTR


class BitBucketRawPullRequestWebhook(BaseModel):
    eventKey: str  # 'pr:modified' / 'pr:opened'
    pullRequest: _BBPlR

    def to_bb(self) -> BitBucketPullRequestWebhook:
        return BitBucketPullRequestWebhook(
            action=PullRequestActionEnum.OPENED if self.eventKey == "pr:opened" else PullRequestActionEnum.REOPENED,
            pull_request=PullRequest(
                number=self.pullRequest.id,
                head=Branch(sha=self.pullRequest.toRef.latestCommit),
                title=self.pullRequest.title,
                body=None,
            ),
            repository=Repo(
                full_name=f"{self.pullRequest.toRef.repository.project.key}/repos/{self.pullRequest.toRef.repository.slug}"
            ),
        )
