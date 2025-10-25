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
    verify_github_webhook,
)
from tests.fixtures.presentation_fixtures.fake_request import make_request
from tests.fixtures.presentation_fixtures.payloads import (
    VALID_BITBUCKET_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


async def test_valid_github_webhook_signature(settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await verify_github_webhook(request=request)

    assert result == body


async def test_missing_github_webhook_signature():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await verify_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert "x-hub-signature-256 header is missing!" in exc_info.value.detail.lower()


async def test_invalid_github_webhook_signature():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(b"invalid_secret", body, hashlib.sha256).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await verify_github_webhook(request=request)

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

    request = await make_request(body=body, headers={})
    result = await parse_bitbucket_webhook(request=request)

    assert isinstance(result, BitBucketRawPullRequestWebhook)


async def test_invalid_json_parse_bitbucket_webhook():
    body = b"broken JSON"
    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_parse_bitbucket_webhook_reviewer_not_needed(settings, monkeypatch):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()
    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "someone_else")

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail


async def test_parse_bitbucket_webhook_event_not_needed(settings, monkeypatch):
    payload = VALID_BITBUCKET_PAYLOAD.copy()
    payload["eventKey"] = "pr:merged"
    body = json.dumps(payload).encode()

    monkeypatch.setattr(settings.GIT_PROVIDER_CONFIG, "GIT_PROVIDER_REVIEWER", "bot")

    request = await make_request(body=body, headers={})

    with pytest.raises(HTTPException) as exc_info:
        await parse_bitbucket_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_200_OK
    assert "Review not needed" in exc_info.value.detail
