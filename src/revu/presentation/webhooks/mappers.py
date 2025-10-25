from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
    GitVersePullRequestWebhook,
)


def github_to_domain(event: GithubPullRequestWebhook) -> PullRequestEventDTO:
    return PullRequestEventDTO(
        action=PullRequestActionEnum(event.action),
        repo_full_name=event.repository.full_name,
        pr_number=event.pull_request.number,
        pr_title=event.pull_request.title,
        pr_body=event.pull_request.body,
        commit_sha=event.pull_request.head.sha,
    )


def gitea_to_domain(event: GiteaPullRequestWebhook) -> PullRequestEventDTO:
    return github_to_domain(event)


def gitverse_to_domain(event: GitVersePullRequestWebhook) -> PullRequestEventDTO:
    return github_to_domain(event)


def bitbucket_to_domain(event: BitBucketPullRequestWebhook) -> PullRequestEventDTO:
    return github_to_domain(event)
