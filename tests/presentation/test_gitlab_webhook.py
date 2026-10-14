"""GitLab authenticates and frames a delivery differently from the other hosts.

GitLab 19.0 and later sign the payload the Standard Webhooks way (``whsec_``
key, ``v1,`` base64 signature over ``id.timestamp.body``); earlier versions send
the shared secret verbatim in ``X-Gitlab-Token``. Both have to work, and the
``update`` action needs the head commit to tell a push from a metadata edit.
"""

import base64
import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from revu.application.services.revision_store import ReviewedRevisionStore
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.validators import (
    ReviewNotNeededError,
    parse_webhook_event,
)
from tests.conftest import GITLAB_SECRET, make_connection
from tests.fixtures.presentation_fixtures.fake_request import make_request

pytestmark = pytest.mark.unit

MESSAGE_ID = "msg-1"
TIMESTAMP = "1700000000"
COMMIT_SHA = "e0a85d5a2275d8e85cbafcc0ec730e51266c1925"


def gitlab_payload(action: str = "open", sha: str | None = COMMIT_SHA) -> dict:
    attributes: dict = {
        "iid": 11,
        "title": "Add feature X",
        "description": "Implements feature X",
        "action": action,
    }

    if sha is not None:
        attributes["last_commit"] = {"id": sha}

    return {
        "object_kind": "merge_request",
        "event_type": "merge_request",
        "object_attributes": attributes,
        "project": {"id": 7, "path_with_namespace": "group/sub/project"},
    }


def body_of(payload: dict) -> bytes:
    return json.dumps(payload).encode()


def signature_for(
    body: bytes,
    token: str = GITLAB_SECRET,
    message_id: str = MESSAGE_ID,
    timestamp: str = TIMESTAMP,
) -> str:
    key = base64.b64decode(token.removeprefix("whsec_"))
    message = b".".join([message_id.encode(), timestamp.encode(), body])

    return "v1," + base64.b64encode(hmac.new(key, message, hashlib.sha256).digest()).decode()


def gitlab_headers(body: bytes, **overrides) -> dict[str, str]:
    headers = {
        "x-gitlab-event": "Merge Request Hook",
        "webhook-id": MESSAGE_ID,
        "webhook-timestamp": TIMESTAMP,
        "webhook-signature": signature_for(body, **overrides),
    }

    return headers


def legacy_headers(body: bytes, token: str = GITLAB_SECRET) -> dict[str, str]:
    return {"x-gitlab-event": "Merge Request Hook", "x-gitlab-token": token}


def gitlab_tenant(make_tenant):
    return make_tenant(make_connection(key="gl-self", host=GitProviderEnum.GITLAB, secret_token=GITLAB_SECRET))


async def test_a_signed_delivery_becomes_a_domain_event(make_tenant):
    body = body_of(gitlab_payload())
    request = await make_request(body=body, headers=gitlab_headers(body))

    event = await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert isinstance(event, PullRequestEventDTO)
    assert event.action == PullRequestActionEnum.OPENED
    assert event.repo_full_name == "group/sub/project"
    assert event.pr_number == 11
    assert event.pr_title == "Add feature X"
    assert event.commit_sha == COMMIT_SHA


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        ("open", PullRequestActionEnum.OPENED),
        ("reopen", PullRequestActionEnum.REOPENED),
        ("update", PullRequestActionEnum.SYNCHRONIZE),
    ],
)
async def test_the_review_actions_are_mapped(make_tenant, action, expected):
    body = body_of(gitlab_payload(action=action))
    request = await make_request(body=body, headers=gitlab_headers(body))

    event = await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert event.action == expected


@pytest.mark.parametrize("action", ["merge", "close", "approved", "unapproved", "unlock"])
async def test_actions_revu_ignores_are_a_quiet_200(make_tenant, action):
    body = body_of(gitlab_payload(action=action))
    request = await make_request(body=body, headers=gitlab_headers(body))

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))


async def test_the_legacy_secret_token_also_authenticates(make_tenant):
    """GitLab before 19.0 sends the shared secret instead of a signature."""
    body = body_of(gitlab_payload())
    request = await make_request(body=body, headers=legacy_headers(body))

    event = await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert event.pr_number == 11


async def test_a_wrong_legacy_token_is_rejected(make_tenant):
    body = body_of(gitlab_payload())
    request = await make_request(body=body, headers=legacy_headers(body, token="wrong-secret"))

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert exc_info.value.status_code == 403


async def test_a_delivery_without_any_credential_is_rejected(make_tenant):
    body = body_of(gitlab_payload())
    request = await make_request(body=body, headers={"x-gitlab-event": "Merge Request Hook"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert exc_info.value.status_code == 403
    assert "webhook-signature" in exc_info.value.detail


async def test_another_connections_signing_token_is_rejected(make_tenant):
    """The isolation property that matters most: secrets are not interchangeable."""
    other = "whsec_" + base64.b64encode(b"a-completely-different-key-0123456").decode()
    body = body_of(gitlab_payload())
    request = await make_request(body=body, headers=gitlab_headers(body, token=other))

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert exc_info.value.status_code == 403


async def test_a_tampered_body_breaks_the_signature(make_tenant):
    body = body_of(gitlab_payload())
    request = await make_request(
        body=body_of(gitlab_payload(action="open", sha="1" * 40)),
        headers=gitlab_headers(body),
    )

    with pytest.raises(HTTPException):
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))


async def test_the_signature_covers_the_timestamp(make_tenant):
    """A captured request cannot be replayed under a new timestamp."""
    body = body_of(gitlab_payload())
    headers = gitlab_headers(body)
    headers["webhook-timestamp"] = "1800000000"
    request = await make_request(body=body, headers=headers)

    with pytest.raises(HTTPException):
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))


async def test_a_signature_among_several_is_enough(make_tenant):
    """Standard Webhooks allows several signatures in one header."""
    body = body_of(gitlab_payload())
    headers = gitlab_headers(body)
    headers["webhook-signature"] = f"v1,bm90LWEtc2lnbmF0dXJl {headers['webhook-signature']}"
    request = await make_request(body=body, headers=headers)

    event = await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert event.pr_number == 11


async def test_a_signing_token_that_is_not_base64_is_a_rejection_not_a_crash(make_tenant):
    """A pasted, malformed signing token must not turn into a 500."""
    body = body_of(gitlab_payload())
    tenant = make_tenant(
        make_connection(
            key="gl-self",
            host=GitProviderEnum.GITLAB,
            secret_token="whsec_not-valid-base64!!",
        )
    )
    request = await make_request(
        body=body,
        headers={
            "x-gitlab-event": "Merge Request Hook",
            "webhook-id": MESSAGE_ID,
            "webhook-timestamp": TIMESTAMP,
            "webhook-signature": "v1,whatever",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await parse_webhook_event(request=request, tenant=tenant)

    assert exc_info.value.status_code == 403


async def test_another_gitlab_event_is_a_quiet_200(make_tenant):
    """GitLab signs every event it sends, so a push arrives authenticated."""
    body = body_of({"object_kind": "push"})
    headers = gitlab_headers(body)
    headers["x-gitlab-event"] = "Push Hook"
    request = await make_request(body=body, headers=headers)

    with pytest.raises(ReviewNotNeededError):
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))


async def test_a_github_payload_on_a_gitlab_connection_is_a_loud_error(make_tenant, caplog):
    """A host mismatch is a configuration mistake, not a delivery to skip."""
    from tests.fixtures.presentation_fixtures.payloads import VALID_WEBHOOK_PAYLOAD

    body = body_of(VALID_WEBHOOK_PAYLOAD)
    request = await make_request(body=body, headers=gitlab_headers(body))

    with caplog.at_level("WARNING"), pytest.raises(ValidationError):
        await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert "check GIT_PROVIDER of connection 'gl-self'" in caplog.text


async def test_a_repeated_update_for_the_same_commit_is_not_reviewed_twice(make_tenant):
    """GitLab sends `update` for a renamed title too, so the commit decides."""
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for _ in range(2):
        payload = gitlab_payload(action="update")
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        if _ == 0:
            assert isinstance(
                await parse_webhook_event(request=request, tenant=tenant, revisions=revisions),
                PullRequestEventDTO,
            )
        else:
            with pytest.raises(ReviewNotNeededError):
                await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)


async def test_a_metadata_edit_after_open_is_not_reviewed_again(make_tenant):
    """`open` records its revision, so the first title edit is a no-op."""
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for action in ("open", "update"):
        payload = gitlab_payload(action=action)
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        if action == "open":
            await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)
        else:
            with pytest.raises(ReviewNotNeededError):
                await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)


async def test_a_new_commit_is_reviewed(make_tenant):
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for sha in (COMMIT_SHA, "1" * 40):
        payload = gitlab_payload(action="update", sha=sha)
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        event = await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)

        assert event.commit_sha == sha


async def test_a_redelivered_open_is_still_reviewed(make_tenant):
    """Only the ambiguous `update` is deduplicated; a redelivery can retry."""
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for _ in range(2):
        payload = gitlab_payload(action="open")
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)


async def test_a_different_merge_request_is_reviewed(make_tenant):
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for iid in (11, 12):
        payload = gitlab_payload(action="update")
        payload["object_attributes"]["iid"] = iid
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        event = await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)

        assert event.pr_number == iid


async def test_a_payload_without_a_commit_is_reviewed(make_tenant):
    """Without a revision to compare, reviewing is the safe answer."""
    revisions = ReviewedRevisionStore()
    tenant = gitlab_tenant(make_tenant)

    for _ in range(2):
        payload = gitlab_payload(action="update", sha=None)
        body = body_of(payload)
        request = await make_request(body=body, headers=gitlab_headers(body))

        await parse_webhook_event(request=request, tenant=tenant, revisions=revisions)


async def test_without_a_store_every_delivery_is_new(make_tenant):
    """A direct call (a test, a script) has no memory to deduplicate with."""
    body = body_of(gitlab_payload(action="update"))
    request = await make_request(body=body, headers=gitlab_headers(body))

    event = await parse_webhook_event(request=request, tenant=gitlab_tenant(make_tenant))

    assert isinstance(event, PullRequestEventDTO)
