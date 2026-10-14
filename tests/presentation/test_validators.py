import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from starlette import status

from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)
from revu.presentation.webhooks.validators import (
    ReviewNotNeededError,
    parse_webhook_event,
)
from tests.conftest import GITEA_SECRET, GITHUB_SECRET, make_connection
from tests.fixtures.presentation_fixtures.fake_request import make_request
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    SOURCE_COMMIT_SHA,
    VALID_BITBUCKET_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


def _digest(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _sign(body: bytes, secret: str) -> dict[str, str]:
    """The header a git host would send for ``body`` and its shared secret."""
    return {"x-hub-signature-256": f"sha256={_digest(body, secret)}"}


async def test_a_signed_github_delivery_becomes_a_domain_event(make_tenant):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    event = await parse_webhook_event(request=request, tenant=tenant)

    assert isinstance(event, PullRequestEventDTO)
    assert event.action == PullRequestActionEnum.OPENED
    assert event.repo_full_name == "CodeOnANapkin/test"
    assert event.pr_number == 12


async def test_the_signature_of_another_connection_does_not_unlock_this_one(make_tenant):
    """The critical isolation property: secrets must not be interchangeable."""
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection(secret_token=GITHUB_SECRET))
    request = await make_request(body=body, headers=_sign(body, GITEA_SECRET))

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "didn't match" in exc_info.value.detail


async def test_a_valid_signature_on_a_later_header_is_accepted(make_tenant):
    """Hosts may send several signature headers; every one of them gets a chance."""
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(
        body=body,
        headers={
            "x-hub-signature-256": "sha256=" + "0" * 64,
            "x-gitea-signature": _digest(body, GITHUB_SECRET),
        },
    )

    assert isinstance(await parse_webhook_event(request=request, tenant=tenant), PullRequestEventDTO)


async def test_a_missing_signature_is_rejected(make_tenant):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "signature header is missing" in exc_info.value.detail.lower()


async def test_the_body_is_not_parsed_before_the_signature_is_checked(make_tenant):
    """A request with a broken body and a bad signature fails on the signature."""
    tenant = make_tenant(make_connection())
    request = await make_request(body=b"not json", headers={"x-hub-signature-256": "sha256=bad"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_a_legacy_sha1_only_header_is_rejected(make_tenant):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers={"x-hub-signature": "sha1=abc123"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_broken_json_is_a_client_error(make_tenant):
    body = b"broken JSON"
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_non_object_json_is_a_client_error(make_tenant):
    body = json.dumps([1, 2, 3]).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


async def test_a_non_pull_request_event_is_ignored(make_tenant):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers={**_sign(body, GITHUB_SECRET), "x-github-event": "push"})

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


async def test_an_action_revu_ignores_is_acknowledged(make_tenant):
    body = json.dumps(INVALID_ACTION_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


@pytest.mark.parametrize("action", ["synchronize", "synchronized", "reopened"])
async def test_every_review_trigger_action_is_accepted(make_tenant, action):
    body = json.dumps({**VALID_WEBHOOK_PAYLOAD, "action": action}).encode()
    tenant = make_tenant(make_connection())
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    assert isinstance(await parse_webhook_event(request=request, tenant=tenant), PullRequestEventDTO)


async def test_a_signed_gitea_delivery_uses_the_gitea_event_header(make_tenant):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection(key="gitea-int", host=GitProviderEnum.GITEA, secret_token=GITEA_SECRET))
    request = await make_request(body=body, headers={**_sign(body, GITEA_SECRET), "x-gitea-event": "push"})

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


async def test_a_payload_that_does_not_match_the_configured_host_is_reported(make_tenant, caplog):
    """The classic misconfiguration: a Gitea payload on a github connection."""
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    tenant = make_tenant(make_connection(host=GitProviderEnum.GITHUB))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with caplog.at_level("WARNING"), pytest.raises(Exception):
        await parse_webhook_event(request=request, tenant=tenant)

    assert "check GIT_PROVIDER of connection 'gh-main'" in caplog.text


@pytest.mark.parametrize("event_key", ["pr:opened", "pr:from_ref_updated"])
async def test_bitbucket_reviews_new_pull_requests_and_new_commits(make_tenant, event_key):
    body = json.dumps({**VALID_BITBUCKET_PAYLOAD, "eventKey": event_key}).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    event = await parse_webhook_event(request=request, tenant=tenant)

    assert event.pr_number == 42
    assert event.repo_full_name == "MYPROJ/repos/my-repo"
    # The reviewed commit is the source branch tip, not the target branch one.
    assert event.commit_sha == SOURCE_COMMIT_SHA


async def test_bitbucket_ignores_metadata_only_updates(make_tenant):
    body = json.dumps({**VALID_BITBUCKET_PAYLOAD, "eventKey": "pr:modified"}).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


async def test_bitbucket_without_reviewers_is_ignored_when_a_reviewer_is_required(make_tenant):
    pull_request = {k: v for k, v in VALID_BITBUCKET_PAYLOAD["pullRequest"].items() if k != "reviewers"}
    body = json.dumps({**VALID_BITBUCKET_PAYLOAD, "pullRequest": pull_request}).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET, reviewer="bot"))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


async def test_bitbucket_reviews_when_no_reviewer_is_configured(make_tenant):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET, reviewer=None))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    assert isinstance(await parse_webhook_event(request=request, tenant=tenant), PullRequestEventDTO)


async def test_bitbucket_reviews_when_the_configured_reviewer_is_listed(make_tenant):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET, reviewer="bot@example.com"))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    assert isinstance(await parse_webhook_event(request=request, tenant=tenant), PullRequestEventDTO)


async def test_bitbucket_ignores_a_delivery_for_another_reviewer(make_tenant):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    tenant = make_tenant(make_connection(key="bb", host=GitProviderEnum.BITBUCKET, reviewer="someone_else"))
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=tenant)


async def test_an_unsupported_host_is_reported(make_tenant):
    """Unreachable through the configuration, but the guard must still hold."""
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    tenant = make_tenant(make_connection(host="sourceforge"))  # type: ignore[arg-type]
    request = await make_request(body=body, headers=_sign(body, GITHUB_SECRET))

    with pytest.raises(UnknownGitProviderException):
        await parse_webhook_event(request=request, tenant=tenant)
