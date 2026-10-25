import base64
import binascii
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
from revu.application.services.revision_store import ReviewedRevisionStore
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
    gitlab_to_domain,
)
from revu.presentation.webhooks.schemas.github_schemas import (
    BitBucketRawPullRequestWebhook,
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)
from revu.presentation.webhooks.schemas.gitlab_schemas import (
    GitLabMergeRequestWebhook,
)

logger = get_logger(name=__name__)

# Delivery kinds each git host distinguishes for pull requests.
PULL_REQUEST_EVENT = "pull_request"

#: Gitea reports commits pushed to a pull request as a delivery kind of its own, with
#: `action: synchronized` inside. Its `pull_request` delivery covers opening, editing
#: and closing only — which is why a webhook with just that one ticked never fires
#: again once the author pushes to the branch.
GITEA_SYNC_EVENT = "pull_request_sync"
GITEA_PR_EVENTS = (PULL_REQUEST_EVENT, GITEA_SYNC_EVENT)
GITHUB_EVENT_HEADER = "x-github-event"
GITEA_EVENT_HEADER = "x-gitea-event"
GITLAB_EVENT_HEADER = "x-gitlab-event"
GITLAB_MERGE_REQUEST_EVENT = "Merge Request Hook"

# GitLab's merge request actions that change the code under review. `update` is
# also sent for metadata edits (gitlab-org/gitlab#10824), so it is the one action
# whose revision has to be checked before a review starts.
GITLAB_REVIEW_ACTIONS = ("open", "reopen", "update")
GITLAB_UPDATE_ACTION = "update"

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

# GitLab 19.0+ signs the delivery the Standard Webhooks way; earlier versions send
# the plain shared secret instead. See _verify_gitlab.
GITLAB_SIGNATURE_HEADER = "webhook-signature"
GITLAB_ID_HEADER = "webhook-id"
GITLAB_TIMESTAMP_HEADER = "webhook-timestamp"
GITLAB_TOKEN_HEADER = "x-gitlab-token"
GITLAB_SIGNING_TOKEN_PREFIX = "whsec_"
GITLAB_SIGNATURE_VERSION = b"v1,"


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


def _gitlab_expected_signature(signing_token: str, body: bytes, message_id: str, timestamp: str) -> bytes | None:
    """Recompute the Standard Webhooks signature GitLab sends.

    The key is the base64 body of the signing token, and the signed message is
    ``id.timestamp.body`` — which is why the timestamp cannot be altered without
    invalidating the signature.
    """
    try:
        key = base64.b64decode(signing_token.removeprefix(GITLAB_SIGNING_TOKEN_PREFIX))
    except (binascii.Error, ValueError):
        return None

    message = b".".join([message_id.encode("utf-8"), timestamp.encode("utf-8"), body])
    digest = hmac.new(key, message, hashlib.sha256).digest()

    return GITLAB_SIGNATURE_VERSION + base64.b64encode(digest)


def _verify_gitlab(request: Request, body: bytes, secret_token: str) -> None:
    """Reject the request unless it proves it came from GitLab.

    GitLab 19.0 and later send an HMAC-SHA256 signature over the payload, which
    authenticates the body. Older versions send the shared secret verbatim in
    ``X-Gitlab-Token``, which only proves the sender knows it — that header is
    replayable and does not bind the body, so the signature is preferred whenever
    it is present.
    """
    signature_header = request.headers.get(GITLAB_SIGNATURE_HEADER)

    if signature_header:
        message_id = request.headers.get(GITLAB_ID_HEADER, "")
        timestamp = request.headers.get(GITLAB_TIMESTAMP_HEADER, "")
        expected = _gitlab_expected_signature(secret_token, body, message_id, timestamp)

        if expected is None or not any(
            hmac.compare_digest(expected, signature.strip().encode("utf-8"))
            for signature in signature_header.split(" ")
            if signature.strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Request signatures didn't match!",
            )

        return

    token_header = request.headers.get(GITLAB_TOKEN_HEADER)

    if token_header and hmac.compare_digest(secret_token, token_header):
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"GitLab token is missing! Expected {GITLAB_TOKEN_HEADER} or {GITLAB_SIGNATURE_HEADER}",
    )


async def _read_verified_body(request: Request, tenant: TenantContext) -> bytes:
    """Read the raw body and check it the way this connection's host signs it."""
    body = await request.body()

    if tenant.config.host == GitProviderEnum.GITLAB:
        _verify_gitlab(request, body, tenant.config.secret_token)
    else:
        _verify_signature(request, body, tenant.config.secret_token)

    return body


def _require_event(
    request: Request,
    header_name: str,
    expected: str | tuple[str, ...] = PULL_REQUEST_EVENT,
) -> None:
    """Ignore deliveries that are not the event this connection reacts to.

    Hosts deliver far more than pull requests to a single webhook URL; those get
    an explicit 200 so they are not retried and do not look like failures. The
    comparison ignores case: GitLab spells its event ``Merge Request Hook``.
    """
    event = request.headers.get(header_name)
    if event is None:
        # Sender doesn't send the header at all — keep legacy behaviour.
        return

    accepted = (expected,) if isinstance(expected, str) else expected

    if event.strip().casefold() not in {value.casefold() for value in accepted}:
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


def _is_gitlab_revision_new(
    event: GitLabMergeRequestWebhook,
    connection_key: str,
    revisions: ReviewedRevisionStore,
) -> bool:
    """Whether this delivery reviews code ReVu has not reviewed yet.

    GitLab sends ``update`` for a renamed title as well as for a push, so the head
    commit decides: the same revision is not reviewed twice. Every trigger records
    its revision, which is what makes the first metadata edit after ``open`` a
    no-op instead of a second review of the same code.
    """
    attributes = event.object_attributes
    revision = attributes.last_commit_sha

    if not revision:
        # Nothing identifies the revision, so reviewing is the safe answer.
        return True

    seen = revisions.has_reviewed(connection_key, event.project.path_with_namespace, attributes.iid, revision)
    revisions.remember(connection_key, event.project.path_with_namespace, attributes.iid, revision)

    return not (seen and attributes.action == GITLAB_UPDATE_ACTION)


async def parse_webhook_event(
    request: Request,
    tenant: TenantContext,
    revisions: ReviewedRevisionStore | None = None,
) -> PullRequestEventDTO:
    """Authenticate and parse a delivery into a domain event.

    The host type comes from the connection configuration, so one function
    handles every host. The body is only read after the per-connection signature
    has been verified. ``revisions`` is the application-wide store the container
    injects; without one (a direct call) every delivery counts as new.
    """
    connection = tenant.config
    revisions = revisions if revisions is not None else ReviewedRevisionStore()
    body = await _read_verified_body(request, tenant)
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
            _require_event(request, GITEA_EVENT_HEADER, GITEA_PR_EVENTS)
            event = _validate(GiteaPullRequestWebhook, payload, connection.key, "Gitea")
            _require_review_action(payload)

            return gitea_to_domain(event)

        case GitProviderEnum.GITLAB:
            _require_event(request, GITLAB_EVENT_HEADER, expected=GITLAB_MERGE_REQUEST_EVENT)
            gitlab_event = _validate(GitLabMergeRequestWebhook, payload, connection.key, "GitLab")

            if gitlab_event.object_attributes.action not in GITLAB_REVIEW_ACTIONS:
                raise ReviewNotNeededError()

            if not _is_gitlab_revision_new(gitlab_event, connection.key, revisions):
                raise ReviewNotNeededError("This revision of the merge request has already been reviewed")

            return gitlab_to_domain(gitlab_event)

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
