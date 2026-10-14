import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException
from starlette import status
from starlette.requests import Request
from starlette.status import HTTP_403_FORBIDDEN

from revu.application.config import get_settings
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)

# Delivery kinds each git host distinguishes for pull requests.
PULL_REQUEST_EVENT = "pull_request"
BITBUCKET_PR_EVENTS = ("pr:modified", "pr:opened")

# Headers carrying an HMAC-SHA256 of the raw body. GitHub and Gitea send the
# GitHub-compatible one, Gitea additionally sends its own, Bitbucket Data
# Center 8.9+ sends `X-Hub-Signature: sha256=<hex>`.
SIGNATURE_HEADERS = ("x-hub-signature-256", "x-gitea-signature", "x-hub-signature")


def _verify_signature(request: Request, body: bytes) -> None:
    """Reject the request unless its HMAC-SHA256 signature matches."""
    secret_token = get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    expected_signature = hmac.new(secret_token.encode("utf-8"), body, hashlib.sha256).hexdigest()

    for header_name in SIGNATURE_HEADERS:
        signature_header = request.headers.get(header_name)
        if not signature_header:
            continue

        if signature_header.startswith("sha1="):
            # Legacy GitHub header; only the sha256 variant is accepted here.
            continue

        # Hosts differ on the framing: `sha256=<hex>` (GitHub, Bitbucket)
        # or a bare hex digest (Gitea).
        candidate = signature_header.removeprefix("sha256=").lower()

        if hmac.compare_digest(expected_signature.encode("utf-8"), candidate.encode("utf-8")):
            return

        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Request signatures didn't match!",
        )

    raise HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail=f"Signature header is missing! Expected one of: {', '.join(SIGNATURE_HEADERS)}",
    )


async def verify_webhook_signature(request: Request) -> bytes:
    """Read the raw body and check it against the configured shared secret.

    The scheme is the same for every supported host, only the header name and
    framing differ.
    """
    body = await request.body()
    _verify_signature(request, body)

    return body


def _require_event(request: Request, header_name: str) -> None:
    """Ignore deliveries that are not pull request events.

    Hosts deliver far more than pull requests to a single webhook URL; those
    get an explicit 200 so they are not retried and do not look like failures.
    """
    event = request.headers.get(header_name)
    if event is None:
        # Sender doesn't send the header at all — keep legacy behaviour.
        return

    if event != PULL_REQUEST_EVENT:
        raise HTTPException(status_code=status.HTTP_200_OK, detail="Review not needed")


def _load_json(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    return payload


def _require_review_action(payload: dict[str, Any]) -> None:
    """Skip actions ReVu never acts on (``closed``, ``labeled``, ...)."""
    if not PullRequestActionEnum.is_review_trigger(str(payload.get("action", ""))):
        raise HTTPException(status_code=status.HTTP_200_OK, detail="Review not needed")


def _is_reviewer_targeted(payload: dict[str, Any]) -> bool:
    reviewer = get_settings().GIT_PROVIDER_CONFIG.get("GIT_PROVIDER_REVIEWER", None)
    if reviewer is None:
        return True

    pull_request = payload.get("pullRequest") or {}
    for entry in pull_request.get("reviewers") or []:
        user = entry.get("user") or {}
        if reviewer in (user.get("name"), user.get("emailAddress"), user.get("displayName")):
            return True

    return False


async def parse_github_webhook(request: Request) -> GithubPullRequestWebhook:
    body = await verify_webhook_signature(request=request)
    _require_event(request, "x-github-event")

    payload_dict = _load_json(body)
    _require_review_action(payload_dict)

    return GithubPullRequestWebhook.model_validate(payload_dict)


async def parse_gitea_webhook(request: Request) -> GiteaPullRequestWebhook:
    body = await verify_webhook_signature(request=request)
    _require_event(request, "x-gitea-event")

    payload_dict = _load_json(body)
    _require_review_action(payload_dict)

    return GiteaPullRequestWebhook.model_validate(payload_dict)


async def parse_bitbucket_webhook(request: Request) -> BitBucketRawPullRequestWebhook:
    body = await verify_webhook_signature(request=request)

    payload_dict = _load_json(body)

    if payload_dict.get("eventKey") not in BITBUCKET_PR_EVENTS:
        raise HTTPException(status_code=status.HTTP_200_OK, detail="Review not needed")

    if not _is_reviewer_targeted(payload_dict):
        raise HTTPException(status_code=status.HTTP_200_OK, detail="Review not needed")

    return BitBucketRawPullRequestWebhook.model_validate(payload_dict)


async def gitverse_validate_authorization(request: Request) -> None:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authorization header with token is missing or invalid",
        )

    secret_token = get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN

    if not hmac.compare_digest(auth_header.encode("utf-8"), secret_token.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization token",
        )
