import pytest
from pydantic import ValidationError

from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketPullRequestWebhook,
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    INVALID_WEBHOOK_PAYLOAD,
    SOURCE_COMMIT_SHA,
    TARGET_COMMIT_SHA,
    VALID_BITBUCKET_PAYLOAD,
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


def test_bitbucket_webhook_schema_accepts_valid_payload():
    schema = BitBucketRawPullRequestWebhook(**VALID_BITBUCKET_PAYLOAD)
    assert isinstance(schema, BitBucketRawPullRequestWebhook)

    bb_schema = schema.to_bb()
    assert isinstance(bb_schema, BitBucketPullRequestWebhook)


def test_bitbucket_maps_the_source_ref_not_the_target_ref():
    """The reviewed commit is the tip of the source branch."""
    schema = BitBucketRawPullRequestWebhook(**VALID_BITBUCKET_PAYLOAD)

    bb_schema = schema.to_bb()

    assert bb_schema.pull_request.head.sha == SOURCE_COMMIT_SHA
    assert bb_schema.pull_request.head.sha != TARGET_COMMIT_SHA
    assert bb_schema.repository.full_name == "MYPROJ/repos/my-repo"


def test_bitbucket_opened_action():
    schema = BitBucketRawPullRequestWebhook(**VALID_BITBUCKET_PAYLOAD)

    assert schema.to_bb().action == PullRequestActionEnum.OPENED


@pytest.mark.parametrize("event_key", ["pr:from_ref_updated", "pr:modified"])
def test_bitbucket_new_commits_map_to_synchronize(event_key):
    schema = BitBucketRawPullRequestWebhook(**{**VALID_BITBUCKET_PAYLOAD, "eventKey": event_key})

    assert schema.to_bb().action == PullRequestActionEnum.SYNCHRONIZE


def test_bitbucket_webhook_schema_without_from_ref_falls_back_to_to_ref():
    pull_request = {k: v for k, v in VALID_BITBUCKET_PAYLOAD["pullRequest"].items() if k != "fromRef"}
    schema = BitBucketRawPullRequestWebhook(**{**VALID_BITBUCKET_PAYLOAD, "pullRequest": pull_request})

    assert schema.to_bb().pull_request.head.sha == TARGET_COMMIT_SHA


def test_github_webhook_schema_keeps_unhandled_action():
    # The schema only checks the payload shape; actions ReVu never acts on are
    # filtered later by the validator so the host gets 200 instead of an error.
    schema = GithubPullRequestWebhook(**INVALID_ACTION_WEBHOOK_PAYLOAD)

    assert schema.action == INVALID_ACTION_WEBHOOK_PAYLOAD["action"]


def test_github_webhook_schema_raises_invalid_payload():
    with pytest.raises(ValidationError) as exc_info:
        GithubPullRequestWebhook(**INVALID_WEBHOOK_PAYLOAD)

    assert "number" in str(exc_info.value)
    assert "repository" in str(exc_info.value)
