import hashlib
import hmac
import json

from fastapi import HTTPException
from starlette.requests import Request
from starlette.status import HTTP_403_FORBIDDEN

from revu.application.config import get_settings
from revu.presentation.webhooks.schemas import GithubPullRequestWebhook


async def verify_and_parse_github_webhook(request: Request):
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

    try:
        payload_dict = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    return GithubPullRequestWebhook.model_validate(payload_dict)
