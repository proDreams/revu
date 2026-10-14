import asyncio
from collections.abc import Mapping
from typing import Any, Literal

import httpx

from revu.application.config import get_logger, get_settings
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HTTPGatewayAttemptLimitExceeded,
    HttpGatewayError,
)

logger = get_logger(name=__name__)

IDEMPOTENT_METHODS = ("GET",)

# Statuses that mean the request was refused before being applied, or that the
# server explicitly asks for a retry later. Retrying them cannot duplicate a
# side effect.
RETRYABLE_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

# Publishing a review is a POST: a 5xx or a gateway timeout may mean the
# comment was already created, so retrying it would publish the review twice.
# Only "definitely not applied" statuses are retried for non-idempotent calls.
RETRYABLE_NON_IDEMPOTENT_STATUSES = frozenset({425, 429, 503})

# Connection-level failures: the request never reached the server.
NOT_SENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

MAX_RETRY_DELAY = 8.0


async def _sleep(seconds: float) -> None:
    """Indirection so tests do not have to wait for real backoff."""
    if seconds > 0:
        await asyncio.sleep(seconds)


class HttpClientGateway:
    """Thin retrying wrapper around a single ``httpx.AsyncClient``.

    Retries are limited to failures that are safe to repeat: idempotent methods
    and statuses that guarantee the request was not applied. This used to retry
    every failure, including 4xx, and every transport error on POST, which could
    publish the same review comment several times.

    The instance is application-scoped; call :meth:`aclose` once when the
    container shuts down.
    """

    def __init__(self) -> None:
        self.timeout = get_settings().HTTP_CLIENT_TIMEOUT
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self.attempts = get_settings().HTTP_CLIENT_REQUEST_ATTEMPTS
        self.backoff = get_settings().get("HTTP_CLIENT_RETRY_BACKOFF", 0.5)

    def _retryable_statuses(self, method: str) -> frozenset[int]:
        return RETRYABLE_STATUSES if method in IDEMPOTENT_METHODS else RETRYABLE_NON_IDEMPOTENT_STATUSES

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        header = response.headers.get("retry-after")
        if not header:
            return None

        try:
            return max(0.0, float(header))
        except ValueError:
            return None

    def _delay(self, attempt: int, response: httpx.Response | None = None) -> float:
        """Exponential backoff, capped, preferring the server's own Retry-After."""
        if response is not None:
            retry_after = self._retry_after_seconds(response)
            if retry_after is not None:
                return min(retry_after, MAX_RETRY_DELAY)

        return min(self.backoff * (2 ** (attempt - 1)), MAX_RETRY_DELAY)

    async def _request(
        self,
        method: Literal["GET", "POST"],
        url: str,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        attempts = self.attempts

        if attempts < 1:
            return None

        retryable_statuses = self._retryable_statuses(method)

        for attempt in range(1, attempts + 1):
            try:
                resp = await self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=headers,
                )
            except httpx.TransportError as exc:
                # A request that was never delivered is safe to repeat whatever
                # the method is; anything else (a read timeout, for instance)
                # may already have been applied.
                is_safe_to_retry = method in IDEMPOTENT_METHODS or isinstance(exc, NOT_SENT_ERRORS)

                if is_safe_to_retry and attempt < attempts:
                    logger.warning("HTTP transport error on %s %s, retrying: %s", method, url, exc)
                    await _sleep(self._delay(attempt))
                    continue

                logger.warning("HTTP transport error on %s %s: %s", method, url, exc)
                raise HTTPGatewayAttemptLimitExceeded(f"Limit exceeded. Last error: {exc}")

            if resp.is_error:
                logger.warning("HTTP %s from %s: %s", resp.status_code, url, resp.text)

                if resp.status_code in retryable_statuses and attempt < attempts:
                    logger.warning("Retrying %s %s after HTTP %s", method, url, resp.status_code)
                    await _sleep(self._delay(attempt, resp))
                    continue

                # A 4xx other than 429 will not become a success by repeating it.
                raise HttpGatewayError(f"HTTP {resp.status_code} from {url}: {resp.text[:300]}")

            if not expect_json:
                return resp.content

            if not resp.content:
                return None

            try:
                return resp.json()
            except Exception:
                logger.error("Non-JSON response: %s", resp.text)
                raise HttpGatewayError(f"Non-JSON response from {url}: {resp.text[:300]}")

    async def post(self, url: str, payload: Any, headers: Mapping[str, str] | None = None) -> Any:
        return await self._request(method="POST", url=url, json=payload, headers=headers)

    async def get(
        self,
        url: str,
        headers: Mapping[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        return await self._request(method="GET", url=url, headers=headers, expect_json=expect_json)

    def get_client(self) -> httpx.AsyncClient:
        return self._client

    async def aclose(self) -> None:
        await self._client.aclose()
