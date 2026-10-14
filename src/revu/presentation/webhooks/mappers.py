from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from revu.presentation.webhooks.schemas.gitlab_schemas import (
    GitLabMergeRequestWebhook,
)

# GitLab names its merge request actions differently. Anything that reaches the
# mapper has already passed the review-trigger gate.
GITLAB_ACTION_TO_DOMAIN = {
    "open": PullRequestActionEnum.OPENED,
    "reopen": PullRequestActionEnum.REOPENED,
    "update": PullRequestActionEnum.SYNCHRONIZE,
}


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


def bitbucket_to_domain(event: BitBucketPullRequestWebhook) -> PullRequestEventDTO:
    return github_to_domain(event)


def gitlab_to_domain(event: GitLabMergeRequestWebhook) -> PullRequestEventDTO:
    attributes = event.object_attributes

    return PullRequestEventDTO(
        action=GITLAB_ACTION_TO_DOMAIN.get(attributes.action, PullRequestActionEnum.SYNCHRONIZE),
        repo_full_name=event.project.path_with_namespace,
        pr_number=attributes.iid,
        pr_title=attributes.title,
        pr_body=attributes.description,
        commit_sha=attributes.last_commit_sha,
    )
