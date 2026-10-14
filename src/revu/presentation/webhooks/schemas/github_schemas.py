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
    # Kept as a plain string: hosts send plenty of actions we simply ignore
    # (``closed``, ``labeled``, ...). Narrowing to the actions that trigger a
    # review happens in the validator, so those deliveries get 200 instead of
    # a validation error.
    action: str
    pull_request: PullRequest
    repository: Repo


class GiteaPullRequestWebhook(GithubPullRequestWebhook):
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
    # `fromRef` is the source branch of the pull request, and therefore the one
    # that carries the reviewed commits. It is optional so a truncated payload
    # still maps instead of failing validation.
    fromRef: _BBTR | None = None


class BitBucketRawPullRequestWebhook(BaseModel):
    eventKey: str  # 'pr:opened' / 'pr:from_ref_updated'
    pullRequest: _BBPlR

    def to_bb(self) -> BitBucketPullRequestWebhook:
        # The reviewed commit is the tip of the source branch (`fromRef`);
        # `toRef` is the target branch, usually the default one. The pull request
        # itself (and therefore its REST path) belongs to the destination
        # repository, which is why `toRef.repository` names the repo.
        reviewed_ref = self.pullRequest.fromRef or self.pullRequest.toRef

        return BitBucketPullRequestWebhook(
            action=PullRequestActionEnum.OPENED if self.eventKey == "pr:opened" else PullRequestActionEnum.SYNCHRONIZE,
            pull_request=PullRequest(
                number=self.pullRequest.id,
                head=Branch(sha=reviewed_ref.latestCommit),
                title=self.pullRequest.title,
                body=None,
            ),
            repository=Repo(
                full_name=f"{self.pullRequest.toRef.repository.project.key}/repos/{self.pullRequest.toRef.repository.slug}"
            ),
        )
