from pydantic import BaseModel


class _GitLabLastCommit(BaseModel):
    id: str = ""


class GitLabObjectAttributes(BaseModel):
    """The merge request itself, as GitLab reports it on a hook delivery."""

    iid: int
    title: str
    # Kept as a plain string: GitLab sends actions ReVu ignores (``approved``,
    # ``merge``, ...). Narrowing to the review triggers happens in the validator,
    # so those deliveries get a quiet 200 instead of a validation error.
    action: str
    description: str | None = None
    last_commit: _GitLabLastCommit | None = None

    @property
    def last_commit_sha(self) -> str:
        """The head commit of the source branch, empty when the payload omits it."""
        return self.last_commit.id if self.last_commit is not None else ""


class GitLabProject(BaseModel):
    path_with_namespace: str


class GitLabMergeRequestWebhook(BaseModel):
    """A payload delivered under ``X-Gitlab-Event: Merge Request Hook``."""

    object_attributes: GitLabObjectAttributes
    project: GitLabProject
