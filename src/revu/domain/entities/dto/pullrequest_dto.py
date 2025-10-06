from dataclasses import dataclass

from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum


@dataclass(frozen=True, slots=True)
class PullRequestEventDTO:
    action: PullRequestActionEnum
    repo_full_name: str
    pr_number: int
    pr_title: str
    commit_sha: str
    pr_body: str | None = None
