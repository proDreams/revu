import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from starlette.testclient import TestClient

from revu.application.app import create_app
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.presentation.webhooks.routes import review_pull_request
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    VALID_BITBUCKET_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


def _sign(body: bytes, settings) -> dict[str, str]:
    secret = settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return {"x-hub-signature-256": f"sha256={digest}"}


@pytest.fixture
def reviews(monkeypatch):
    """Record every review the background task would have started."""
    processed: list[PullRequestEventDTO] = []

    async def fake_process(self, webhook_data: PullRequestEventDTO) -> None:
        processed.append(webhook_data)

    monkeypatch.setattr(WebhookService, "process_webhook", fake_process)

    return processed


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


async def test_github_webhook_starts_review(client, reviews, settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/github", content=body, headers=_sign(body, settings))

    assert response.status_code == 200
    assert [review.repo_full_name for review in reviews] == ["CodeOnANapkin/test"]
    assert reviews[0].pr_number == 12


async def test_github_webhook_ignores_unhandled_action(client, reviews, settings):
    body = json.dumps(INVALID_ACTION_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/github", content=body, headers=_sign(body, settings))

    assert response.status_code == 200
    assert response.json() == {"detail": "Review not needed"}
    assert reviews == []


async def test_github_webhook_ignores_other_events(client, reviews, settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    headers = {**_sign(body, settings), "x-github-event": "push"}

    response = client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert reviews == []


async def test_github_webhook_rejects_bad_signature(client, reviews, settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/github", content=body, headers={"x-hub-signature-256": "sha256=bad"})

    assert response.status_code == 403
    assert reviews == []


async def test_github_webhook_returns_422_for_malformed_payload(client, reviews, settings):
    body = json.dumps({"action": "opened"}).encode()

    response = client.post("/webhooks/github", content=body, headers=_sign(body, settings))

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing"
    assert reviews == []


async def test_gitea_webhook_starts_review(client, reviews, settings):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gitea", content=body, headers=_sign(body, settings))

    assert response.status_code == 200
    assert len(reviews) == 1


async def test_bitbucket_webhook_starts_review(client, reviews, settings):
    body = json.dumps(VALID_BITBUCKET_PAYLOAD).encode()

    response = client.post("/webhooks/bitbucket", content=body, headers=_sign(body, settings))

    assert response.status_code == 200
    assert len(reviews) == 1
    assert reviews[0].pr_number == 42
    assert reviews[0].repo_full_name == "MYPROJ/repos/my-repo"


async def test_gitverse_webhook_reports_not_implemented(client, settings):
    headers = {
        "authorization": settings.GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN,
        "content-type": "application/json",
    }

    response = client.post("/webhooks/gitverse", json=VALID_WEBHOOK_PAYLOAD, headers=headers)

    assert response.status_code == 501
    assert "not implemented" in response.json()["detail"]


async def test_gitverse_webhook_rejects_missing_token(client):
    response = client.post("/webhooks/gitverse", json=VALID_WEBHOOK_PAYLOAD)

    assert response.status_code == 403


async def test_review_task_swallows_errors_instead_of_killing_the_worker(caplog):
    service = AsyncMock()
    service.process_webhook.side_effect = RuntimeError("boom")

    event = PullRequestEventDTO(
        action="opened",  # type: ignore[arg-type]
        repo_full_name="owner/repo",
        pr_number=3,
        pr_title="t",
        commit_sha="a" * 40,
    )

    with caplog.at_level("ERROR"):
        await review_pull_request(service, event)  # type: ignore[arg-type]

    service.process_webhook.assert_awaited_once()
    assert "Review failed for owner/repo#3" in caplog.text
