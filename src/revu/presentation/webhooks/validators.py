import hashlib
import hmac
import json

from fastapi import HTTPException
from starlette import status
from starlette.requests import Request
from starlette.status import HTTP_403_FORBIDDEN

from revu.application.config import get_settings
from revu.presentation.webhooks.routes import BitBucketRawPullRequestWebhook
from revu.presentation.webhooks.schemas.github_schemas import (
    GiteaPullRequestWebhook,
    GithubPullRequestWebhook,
)


async def verify_github_webhook(request: Request) -> bytes:
    signature_header = request.headers.get("x-hub-signature-256")
    if not signature_header:
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="x-hub-signature-256 header is missing!",
        )

    body = await request.body()

    secret_token = get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN
    hash_object = hmac.new(secret_token.encode("utf-8"), msg=body, digestmod=hashlib.sha256)

    expected_signature = f"sha256={hash_object.hexdigest()}"
    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(
            status_code=HTTP_403_FORBIDDEN,
            detail="Request signatures didn't match!",
        )

    return body


async def parse_github_webhook(request: Request) -> GithubPullRequestWebhook:
    body = await verify_github_webhook(request=request)

    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return GithubPullRequestWebhook.model_validate(payload_dict)


async def parse_bitbucket_webhook(request: Request) -> BitBucketRawPullRequestWebhook:
    body = await request.body()

    try:
        payload_dict = json.loads(body)
        reviewer = get_settings().GIT_PROVIDER_CONFIG.get("GIT_PROVIDER_REVIEWER", None)
        if reviewer is not None:
            if (
                reviewer not in [k["user"]["name"] for k in payload_dict["pullRequest"]["reviewers"]]
                and reviewer not in [k["user"]["emailAddress"] for k in payload_dict["pullRequest"]["reviewers"]]
                and reviewer not in [k["user"]["displayName"] for k in payload_dict["pullRequest"]["reviewers"]]
            ):
                raise HTTPException(status_code=200, detail="Review not needed")
        if payload_dict["eventKey"] not in ("pr:modified", "pr:opened"):
            raise HTTPException(status_code=200, detail="Review not needed")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return BitBucketRawPullRequestWebhook.model_validate(payload_dict)


async def parse_gitea_webhook(request: Request) -> GiteaPullRequestWebhook:
    body = await verify_github_webhook(request=request)

    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return GiteaPullRequestWebhook.model_validate(payload_dict)


async def gitverse_validate_authorization(request: Request) -> None:
    auth_header = request.headers.get("authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authorization header with token is missing or invalid",
        )

    secret_token = get_settings().GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN

    if auth_header != secret_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid authorization token",
        )
