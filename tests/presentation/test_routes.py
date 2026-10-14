import hashlib
import hmac
import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from revu.application.app import _core_exception_handler, create_app
from revu.application.services.webhook_service import WebhookService
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.exceptions.base import CoreException
from revu.presentation.webhooks.routes import review_pull_request
from tests.conftest import BITBUCKET_SECRET, GITEA_SECRET, GITHUB_SECRET
from tests.fixtures.presentation_fixtures.payloads import (
    INVALID_ACTION_WEBHOOK_PAYLOAD,
    SOURCE_COMMIT_SHA,
    VALID_BITBUCKET_PAYLOAD,
    VALID_WEBHOOK_PAYLOAD,
)

pytestmark = pytest.mark.unit


def _sign(body: bytes, secret: str) -> dict[str, str]:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    return {"x-hub-signature-256": f"sha256={digest}"}


@pytest.fixture
def reviews(monkeypatch):
    """Record every review the background task would have started."""
    processed: list[tuple[str, PullRequestEventDTO]] = []

    async def fake_process(self, tenant, webhook_data) -> None:
        processed.append((tenant.key, webhook_data))

    monkeypatch.setattr(WebhookService, "process_webhook", fake_process)

    return processed


@pytest.fixture
def client(app_settings):
    with TestClient(create_app()) as test_client:
        yield test_client


def test_a_signed_github_delivery_starts_a_review(client, reviews):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gh-main", content=body, headers=_sign(body, GITHUB_SECRET))

    assert response.status_code == 200
    assert [key for key, _ in reviews] == ["gh-main"]
    assert reviews[0][1].repo_full_name == "CodeOnANapkin/test"
    assert reviews[0][1].pr_number == 12


def test_a_signed_gitea_delivery_starts_a_review_on_its_own_connection(client, reviews):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gitea-int", content=body, headers=_sign(body, GITEA_SECRET))

    assert response.status_code == 200
    assert [key for key, _ in reviews] == ["gitea-int"]


def test_a_signature_is_only_valid_for_its_own_connection(client, reviews):
    """The route-level half of the secret-isolation guarantee."""
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gitea-int", content=body, headers=_sign(body, GITHUB_SECRET))

    assert response.status_code == 403
    assert reviews == []


def test_an_unknown_connection_is_a_404(client, reviews):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/does-not-exist", content=body, headers=_sign(body, GITHUB_SECRET))

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown webhook connection"}
    assert reviews == []


def test_an_unrelated_event_is_acknowledged(client, reviews):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()
    headers = {**_sign(body, GITHUB_SECRET), "x-github-event": "push"}

    response = client.post("/webhooks/gh-main", content=body, headers=headers)

    assert response.status_code == 200
    assert reviews == []


def test_an_action_revu_ignores_is_acknowledged(client, reviews):
    body = json.dumps(INVALID_ACTION_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gh-main", content=body, headers=_sign(body, GITHUB_SECRET))

    assert response.status_code == 200
    assert response.json() == {"detail": "Review not needed"}
    assert reviews == []


def test_a_bad_signature_is_rejected(client, reviews):
    body = json.dumps(VALID_WEBHOOK_PAYLOAD).encode()

    response = client.post("/webhooks/gh-main", content=body, headers={"x-hub-signature-256": "sha256=bad"})

    assert response.status_code == 403
    assert reviews == []


def test_a_malformed_payload_is_a_422(client, reviews):
    body = json.dumps({"action": "opened"}).encode()

    response = client.post("/webhooks/gh-main", content=body, headers=_sign(body, GITHUB_SECRET))

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "missing"
    assert reviews == []


def test_a_bitbucket_connection_reviews_new_commits(client, reviews):
    body = json.dumps({**VALID_BITBUCKET_PAYLOAD, "eventKey": "pr:from_ref_updated"}).encode()

    response = client.post("/webhooks/bb-client", content=body, headers=_sign(body, BITBUCKET_SECRET))

    assert response.status_code == 200
    assert [key for key, _ in reviews] == ["bb-client"]
    assert reviews[0][1].commit_sha == SOURCE_COMMIT_SHA


def test_health_endpoint(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_review_task_swallows_errors_instead_of_killing_the_worker(caplog, tenant):
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
        await review_pull_request(service, tenant, event)  # type: ignore[arg-type]

    service.process_webhook.assert_awaited_once()
    assert "Review failed for connection gh-main" in caplog.text
    assert "owner/repo#3" in caplog.text


class _Boom(CoreException):
    pass


def test_domain_exception_is_reported_as_a_generic_500():
    """A CoreException used to fall through to an opaque Starlette 500."""
    app = FastAPI()
    app.add_exception_handler(CoreException, _core_exception_handler)

    @app.get("/boom")
    async def boom() -> None:
        raise _Boom("no review mode")

    with TestClient(app) as test_client:
        response = test_client.get("/boom")

    assert response.status_code == 500
    # Internals are logged, not returned to the caller.
    assert response.json() == {"detail": "Internal application error"}
