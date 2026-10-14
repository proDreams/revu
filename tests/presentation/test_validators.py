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
    gitverse_validate_authorization,
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


def _sign(body: bytes, settings) -> dict[str, str]:
    """Build the HMAC-SHA256 header a git host would send for ``body``."""
    secret = settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return {"x-hub-signature-256": f"sha256={digest}"}


async def test_valid_github_webhook_signature(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await verify_webhook_signature(request=request)

    assert result == body


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


async def test_valid_parse_github_webhook(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await parse_github_webhook(request=request)

    assert isinstance(result, GithubPullRequestWebhook)


async def test_valid_parse_gitea_webhook(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await parse_gitea_webhook(request=request)

    assert isinstance(result, GiteaPullRequestWebhook)


async def test_invalid_parse_github_webhook(settings):
    body = b"broken JSON"
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_invalid_parse_gitea_webhook(settings):
    body = b"broken JSON"
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_gitea_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_valid_gitverse_authorization(settings):
    request = await make_request(
        body=b"", headers={"authorization": settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN}
    )

    await gitverse_validate_authorization(request=request)


async def test_missing_gitverse_authorization():
    request = await make_request(body=b"", headers={})

    with pytest.raises(HTTPException) as exc_info:
        await gitverse_validate_authorization(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Authorization header with token is missing or invalid" in exc_info.value.detail


async def test_invalid_gitverse_authorization():
    request = await make_request(body=b"", headers={"authorization": "invalid_secret"})

    with pytest.raises(HTTPException) as exc_info:
        await gitverse_validate_authorization(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Invalid authorization token" in exc_info.value.detail


async def test_valid_parse_bitbucket_webhook(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()

    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))
    result = await parse_bitbucket_webhook(request=request)

    assert isinstance(result, BitBucketRawPullRequestWebhook)


async def test_bitbucket_webhook_without_signature_is_rejected(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


async def test_bitbucket_webhook_with_bad_signature_is_rejected(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

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
    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "someone_else")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail


async def test_parse_bitbucket_webhook_event_not_needed(settings, monkeypatch):
    payload = VALID_BITBUCKET_PAYLOAD.copy()
    payload["eventKey"] = "pr:merged"
    body = json.dumps(payload).encode()

    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail


async def test_parse_bitbucket_webhook_without_reviewers(settings, monkeypatch):
    payload = VALID_BITBUCKET_PAYLOAD.copy()
    payload["pullRequest"] = {k: v for k, v in payload["pullRequest"].items() if k != "reviewers"}
    body = json.dumps(payload).encode()

    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    # Used to raise KeyError because "reviewers" was read unconditionally.
    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK


async def test_parse_bitbucket_webhook_without_event_key(settings, monkeypatch):
    payload = VALID_BITBUCKET_PAYLOAD.copy()
    del payload["eventKey"]
    body = json.dumps(payload).encode()

    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK


async def test_parse_github_webhook_ignores_unhandled_action(settings):
    body = json.dumps(INVALID_ACTION_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail


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

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail


async def test_parse_github_webhook_without_event_header_is_processed(settings):
    # Senders that don't send X-GitHub-Event keep the legacy behaviour.
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_github_webhook(request=request), GithubPullRequestWebhook)


async def test_parse_github_webhook_accepts_gitea_signature_header(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    secret = settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    # Gitea's native header carries the bare hex digest without a `sha256=` prefix.
    request = await make_request(body=body, headers={"x-gitea-signature": digest})

    assert isinstance(await parse_github_webhook(request=request), GithubPullRequestWebhook)


async def test_github_webhook_signature_accepts_sha256_prefix(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    assert (
        await verify_webhook_signature(request=await make_request(body=body, headers=_sign(body, settings)))
    ) == body


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
    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", None)

    request = await make_request(body=body, headers=_sign(body, settings))

    assert isinstance(await parse_bitbucket_webhook(request=request), BitBucketRawPullRequestWebhook)
