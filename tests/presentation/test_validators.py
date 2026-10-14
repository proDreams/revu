import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from starlette import status

from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from revu.presentation.webhooks.validators import (
    ReviewNotNeededError,
    parse_bitbucket_webhook,
    parse_gitea_webhook,
    parse_github_webhook,
    verify_webhook_signature,
)
from tests.fixtures.presentation_fixtures.fake_request import make_request
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    VALID_BITBUCKET_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


def _digest(body: bytes, settings) -> str:
    secret = settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _sign(body: bytes, settings) -> dict[str, str]:
    """Build the HMAC-SHA256 header a git host would send for ``body``."""
    return {"x-hub-signature-256": f"sha256={_digest(body, settings)}"}


async def test_valid_github_webhook_signature(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    signed = await make_request(body=body, headers=_sign(body, settings))

    assert (await verify_webhook_signature(request=signed)) == body


async def test_missing_github_webhook_signature():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await verify_webhook_signature(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "signature header is missing" in exc_info.value.detail.lower()
    assert "x-hub-signature-256" in exc_info.value.detail


async def test_invalid_github_webhook_signature():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(b"invalid_secret", body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await verify_webhook_signature(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Request signatures didn't match!" in exc_info.value.detail


async def test_a_valid_signature_on_a_later_header_is_accepted(settings):
    """Hosts may send several signature headers; every one of them gets a chance."""
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(
        body=body,
        headers={
            "x-hub-signature-256": "sha256=" + "0" * 64,
            "x-gitea-signature": _digest(body, settings),
        },
    )

    assert (await verify_webhook_signature(request=request)) == body


async def test_valid_parse_github_webhook(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    result = await parse_github_webhook(request=request)

    assert isinstance(result, GithubPullRequestWebhook)


async def test_valid_parse_gitea_webhook(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    result = await parse_gitea_webhook(request=request)

    assert isinstance(result, GiteaPullRequestWebhook)


async def test_invalid_parse_github_webhook(settings):
    body = b"broken JSON"

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_invalid_parse_gitea_webhook(settings):
    body = b"broken JSON"

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_gitea_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_valid_parse_bitbucket_webhook(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))
    result = await parse_bitbucket_webhook(request=request)

    assert isinstance(result, BitBucketRawPullRequestWebhook)


@pytest.mark.parametrize("event_key", ["pr:opened", "pr:from_ref_updated"])
async def test_bitbucket_reviews_new_pull_requests_and_new_commits(settings, monkeypatch, event_key):
    """`pr:from_ref_updated` is how Bitbucket announces commits pushed to a PR."""
    payload = {**VALID_BITBUCKET_PAYLOAD, "eventKey": event_key}
    body = json.dumps(payload).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_bitbucket_webhook(request=request), BitBucketRawPullRequestWebhook)


async def test_bitbucket_ignores_metadata_only_updates(settings, monkeypatch):
    """`pr:modified` means the title/description changed, not the code."""
    payload = {**VALID_BITBUCKET_PAYLOAD, "eventKey": "pr:modified"}
    body = json.dumps(payload).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(ReviewNotNeededError):
        await parse_bitbucket_webhook(request=request)


async def test_bitbucket_webhook_without_signature_is_rejected(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_bitbucket_webhook_with_bad_signature_is_rejected(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers={"x-hub-signature-256": "sha256=deadbeef"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_invalid_json_parse_bitbucket_webhook(settings):
    body = b"broken JSON"
    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_parse_bitbucket_webhook_reviewer_not_needed(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "someone_else")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(ReviewNotNeededError) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert "Review not needed" in str(exc_info.value)


async def test_parse_bitbucket_webhook_event_not_needed(settings, monkeypatch):
    payload = {**VALID_BITBUCKET_PAYLOAD, "eventKey": "pr:merged"}
    body = json.dumps(payload).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(ReviewNotNeededError) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert "Review not needed" in str(exc_info.value)


async def test_parse_bitbucket_webhook_without_reviewers(settings, monkeypatch):
    pull_request = {k: v for k, v in VALID_BITBUCKET_PAYLOAD["pullRequest"].items() if k != "reviewers"}
    payload = {**VALID_BITBUCKET_PAYLOAD, "pullRequest": pull_request}
    body = json.dumps(payload).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    # Used to raise KeyError because "reviewers" was read unconditionally.
    with pytest.raises(ReviewNotNeededError):
        await parse_bitbucket_webhook(request=request)


async def test_parse_bitbucket_webhook_without_event_key(settings, monkeypatch):
    payload = {k: v for k, v in VALID_BITBUCKET_PAYLOAD.items() if k != "eventKey"}
    body = json.dumps(payload).encode()

    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(ReviewNotNeededError):
        await parse_bitbucket_webhook(request=request)


async def test_parse_github_webhook_ignores_unhandled_action(settings):
    body = json.dumps(INVALID_ACTION_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(ReviewNotNeededError) as exc_info:
        await parse_github_webhook(request=request)

    assert "Review not needed" in str(exc_info.value)


@pytest.mark.parametrize(
    "payload",
    [
        {**VALID_WEBHOOK_PAYLOAD, "action": "synchronize"},
        {**VALID_WEBHOOK_PAYLOAD, "action": "synchronized"},
        {**VALID_WEBHOOK_PAYLOAD, "action": "reopened"},
    ],
)
async def test_parse_github_webhook_accepts_review_trigger_actions(settings, payload):
    body = json.dumps(payload).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_github_webhook(request=request), GithubPullRequestWebhook)


async def test_parse_github_webhook_ignores_non_pull_request_event(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers={**_sign(body, settings), "x-github-event": "push"})

    with pytest.raises(ReviewNotNeededError) as exc_info:
        await parse_github_webhook(request=request)

    assert "Review not needed" in str(exc_info.value)


async def test_parse_github_webhook_without_event_header_is_processed(settings):
    # Senders that don't send X-GitHub-Event keep the legacy behaviour.
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_github_webhook(request=request), GithubPullRequestWebhook)


async def test_parse_github_webhook_accepts_gitea_signature_header(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    # Gitea's native header carries the bare hex digest without a `sha256=` prefix.
    request = await make_request(body=body, headers={"x-gitea-signature": _digest(body, settings)})

    assert isinstance(await parse_github_webhook(request=request), GithubPullRequestWebhook)


async def test_signature_rejects_legacy_sha1_header(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers={"x-hub-signature": "sha1=abc123"})

    with pytest.raises(HTTPException) as exc_info:
        await verify_webhook_signature(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_parse_github_webhook_rejects_non_object_json(settings):
    body = json.dumps([1, 2, 3]).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_parse_bitbucket_webhook_without_reviewer_configured(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setitem(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", None)

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_bitbucket_webhook(request=request), BitBucketRawPullRequestWebhook)
