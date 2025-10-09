import pytest
from pydantic import ValidationError

from revu.presentation.webhooks.schemas.github_schemas import (
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
    GitVersePullRequestWebhook,
)
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    INVALID_WEBHOOK_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


def test_github_webhook_schema_accepts_valid_payload():
    schema = GithubPullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)

    assert isinstance(schema, GithubPullRequestWebhook)
    assert schema.action == VALID_WEBHOOK_PAYLOAD["action"]


def test_gitea_webhook_schema_accepts_valid_payload():
    schema = GiteaPullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    assert isinstance(schema, GiteaPullRequestWebhook)


def test_gitverse_webhook_schema_accepts_valid_payload():
    schema = GitVersePullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    assert isinstance(schema, GitVersePullRequestWebhook)


def test_github_webhook_schema_raises_invalid_action():
    with pytest.raises(ValidationError):
        GithubPullRequestWebhook(**INVALID_ACTION_WEBHOOK_PAYLOAD)


def test_github_webhook_schema_raises_invalid_payload():
    with pytest.raises(ValidationError) as exc_info:
        GithubPullRequestWebhook(**INVALID_WEBHOOK_PAYLOAD)

    assert "number" in str(exc_info.value)
    assert "repository" in str(exc_info.value)
