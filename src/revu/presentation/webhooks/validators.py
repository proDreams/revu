import hashlib
import hmac
import json
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from starlette import status
from starlette.requests import Request

from revu.application.config import get_logger
from revu.application.entities.tenant import TenantContext
from revu.domain.entities.dto.pullrequest_dto import PullRequestEventDTO
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.domain.entities.enums.pullrequest_enums import PullRequestActionEnum
from revu.domain.entities.exceptions.git_provider_exceptions import (
    UnknownGitProviderException,
)
from revu.presentation.webhooks.mappers import (
    bitbucket_to_domain,
    gitea_to_domain,
    github_to_domain,
)
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)

logger = get_logger(name=__name__)

# Delivery kinds each git host distinguishes for pull requests.
PULL_REQUEST_EVENT = "pull_request"
GITHUB_EVENT_HEADER = "x-github-event"
GITEA_EVENT_HEADER = "x-gitea-event"

# Bitbucket Data Center delivers `pr:opened` for a new pull request and
# `pr:from_ref_updated` when commits are pushed to its source branch. Those are
# the two events that change the code under review; `pr:modified` only means the
# pull request metadata (title, description, target branch) changed, so it must
# not trigger a review of an unchanged diff.
BITBUCKET_PR_EVENTS = ("pr:opened", "pr:from_ref_updated")

# Headers carrying an HMAC-SHA256 of the raw body. GitHub and Gitea send the
# GitHub-compatible one, Gitea additionally sends its own, Bitbucket Data
# Center 8.9+ sends `X-Hub-Signature: sha256=<hex>`.
SIGNATURE_HEADERS = ("x-hub-signature-256", "x-gitea-signature", "x-hub-signature")


class ReviewNotNeededError(Exception):
    """An authentic delivery that ReVu has nothing to do for.

    The routes turn this into ``200 OK`` so hosts do not retry. Raising
    ``HTTPException`` with a 2xx status (the previous approach) was misleading
    and depended on Starlette's fallback handler lookup.
    """

    def __init__(self, reason: str = "Review not needed") -> None:
        self.reason = reason
        super().__init__(reason)


def _verify_signature(request: Request, body: bytes, secret_token: str) -> None:
    """Reject the request unless one of its HMAC-SHA256 signatures matches.

    Every present signature header is tried: hosts can send more than one (Gitea
    sends both its native header and the GitHub-compatible one), and rejecting
    on the first header that happens to be present broke valid deliveries whose
    matching header came second.
    """
    expected_signature = hmac.new(secret_token.encode("utf-8"), body, hashlib.sha256).hexdigest()

    found_signature_header = False

    for header_name in SIGNATURE_HEADERS:
        signature_header = request.headers.get(header_name)
        if not signature_header:
            continue

        if signature_header.startswith("sha1="):
            # Legacy GitHub header; only the sha256 variant is accepted here.
            continue

        found_signature_header = True

        # Hosts differ on the framing: `sha256=<hex>` (GitHub, Bitbucket)
        # or a bare hex digest (Gitea).
        candidate = signature_header.removeprefix("sha256=").strip().lower()

        if hmac.compare_digest(expected_signature, candidate):
            return

    if not found_signature_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Signature header is missing! Expected one of: {', '.join(SIGNATURE_HEADERS)}",
        )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Request signatures didn't match!",
    )


async def _read_verified_body(request: Request, secret_token: str) -> bytes:
    """Read the raw body and check it against this connection's shared secret."""
    body = await request.body()
    _verify_signature(request, body, secret_token)

    return body


def _require_event(request: Request, header_name: str) -> None:
    """Ignore deliveries that are not pull request events.

    Hosts deliver far more than pull requests to a single webhook URL; those get
    an explicit 200 so they are not retried and do not look like failures.
    """
    event = request.headers.get(header_name)
    if event is None:
        # Sender doesn't send the header at all — keep legacy behaviour.
        return

    if event != PULL_REQUEST_EVENT:
        raise ReviewNotNeededError()


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
        raise ReviewNotNeededError()


def _is_reviewer_targeted(payload: dict[str, Any], reviewer: str | None) -> bool:
    if reviewer is None:
        return True

    pull_request = payload.get("pullRequest") or {}
    for entry in pull_request.get("reviewers") or []:
        user = entry.get("user") or {}
        if reviewer in (user.get("name"), user.get("emailAddress"), user.get("displayName")):
            return True

    return False


async def parse_webhook_event(request: Request, tenant: TenantContext) -> PullRequestEventDTO:
    """Authenticate and parse a delivery into a domain event.

    The host type comes from the connection configuration, so one function
    handles every host. The body is only read after the per-connection signature
    has been verified.
    """
    connection = tenant.config
    body = await _read_verified_body(request, connection.secret_token)
    payload = _load_json(body)

    # Order matters. The delivery kind (header for GitHub/Gitea, `eventKey` for
    # Bitbucket) is checked first so unrelated deliveries stay a quiet 200. The
    # payload shape is validated next, *before* the action gate: a payload that
    # does not match the configured host is a configuration mistake and deserves
    # a loud 422, whereas an action ReVu ignores is a deliberate 200. Checking
    # the action first would swallow the former as the latter.
    match connection.host:
        case GitProviderEnum.GITHUB:
            _require_event(request, GITHUB_EVENT_HEADER)
            event = _validate(GithubPullRequestWebhook, payload, connection.key, "GitHub")
            _require_review_action(payload)

            return github_to_domain(event)

        case GitProviderEnum.GITEA:
            _require_event(request, GITEA_EVENT_HEADER)
            event = _validate(GiteaPullRequestWebhook, payload, connection.key, "Gitea")
            _require_review_action(payload)

            return gitea_to_domain(event)

        case GitProviderEnum.BITBUCKET:
            if payload.get("eventKey") not in BITBUCKET_PR_EVENTS:
                raise ReviewNotNeededError()

            raw = _validate(BitBucketRawPullRequestWebhook, payload, connection.key, "Bitbucket")

            if not _is_reviewer_targeted(payload, connection.reviewer):
                raise ReviewNotNeededError()

            return bitbucket_to_domain(raw.to_bb())

        case _:
            # Unreachable: the configuration validator rejects other hosts.
            raise UnknownGitProviderException(f"Unknown git provider {connection.host!r}")


def _validate[ModelT: BaseModel](
    model: type[ModelT],
    payload: dict[str, Any],
    connection_key: str,
    host_label: str,
) -> ModelT:
    """Validate the payload, explaining a host mismatch in the log.

    A connection whose ``GIT_PROVIDER`` does not match the webhook pointing at it
    is a configuration mistake, and without this note it only shows up as a
    generic 422.
    """
    try:
        return model.model_validate(payload)
    except Exception:
        logger.warning(
            "payload does not look like a %s pull request event; check GIT_PROVIDER of connection %r",
            host_label,
            connection_key,
        )
        raise
