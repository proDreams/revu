import hashlib
import hmac
import json

import pytest
from fastapi import HTTPException
from starlette import status

from revu.application.config import get_settings
from revu.presentation.webhooks.schemas.github_schemas import (
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from revu.presentation.webhooks.validators import (
    gitverse_validate_authorization,
    parse_gitea_webhook,
    parse_github_webhook,
    verify_github_webhook,
)
from tests.fixtures.presentation_fixtures.fake_request import make_request
from tests.fixtures.presentation_fixtures.payloads import VALID_WEBHOOK_PAYLOAD

pytestmark = pytest.mark.unit


async def test_valid_github_webhook_signature():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(
        get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256
    ).hexdigest()

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


async def test_valid_parse_github_webhook():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(
        get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256
    ).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await parse_github_webhook(request=request)

    assert isinstance(result, GithubPullRequestWebhook)


async def test_valid_parse_gitea_webhook():
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    sig = hmac.new(
        get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256
    ).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    result = await parse_gitea_webhook(request=request)

    assert isinstance(result, GiteaPullRequestWebhook)


async def test_invalid_parse_github_webhook():
    body = b"broken JSON"
    sig = hmac.new(
        get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256
    ).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_github_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_invalid_parse_gitea_webhook():
    body = b"broken JSON"
    sig = hmac.new(
        get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN.encode(), body, hashlib.sha256
    ).hexdigest()

    request = await make_request(body=body, headers={"x-hub-signature-256": f"sha256={sig}"})

    with pytest.raises(HTTPException) as exc_info:
        await parse_gitea_webhook(request=request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Invalid JSON payload" in exc_info.value.detail


async def test_valid_gitverse_authorization():
    request = await make_request(
        body=b"", headers={"authorization": get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN}
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
