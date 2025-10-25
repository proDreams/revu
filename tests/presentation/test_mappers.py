import pytest

from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.mappers import (
    bitbucket_to_domain,
    gitea_to_domain,
    github_to_domain,
    gitverse_to_domain,
)
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
    GitVersePullRequestWebhook,
)
from tests.fixtures.presentation_fixtures.payloads import VALID_WEBHOOK_PAYLOAD

pytestmark = pytest.mark.unit


def test_github_to_domain_maps_all_fields():
    schema = GithubPullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    dto = github_to_domain(event=schema)

    assert isinstance(dto, PullRequestEventDTO)

    assert dto.action == PullRequestActionEnum.OPENED
    assert dto.repo_full_name == VALID_WEBHOOK_PAYLOAD["repository"]["full_name"]
    assert dto.pr_number == VALID_WEBHOOK_PAYLOAD["pull_request"]["number"]
    assert dto.pr_title == VALID_WEBHOOK_PAYLOAD["pull_request"]["title"]
    assert dto.pr_body == VALID_WEBHOOK_PAYLOAD["pull_request"]["body"]
    assert dto.commit_sha == VALID_WEBHOOK_PAYLOAD["pull_request"]["head"]["sha"]


def test_gitea_to_domain_uses_same_mapping():
    schema = GiteaPullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    dto = gitea_to_domain(event=schema)
    assert isinstance(dto, PullRequestEventDTO)


def test_gitverse_to_domain_uses_same_mapping():
    schema = GitVersePullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    dto = gitverse_to_domain(event=schema)
    assert isinstance(dto, PullRequestEventDTO)


def test_bitbucket_to_domain_uses_same_mapping():
    schema = BitBucketPullRequestWebhook(**VALID_WEBHOOK_PAYLOAD)
    dto = bitbucket_to_domain(event=schema)
    assert isinstance(dto, PullRequestEventDTO)
