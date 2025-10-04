from collections.abc import Mapping
from typing import Any, Literal

import httpx

from revu.application.base.singleton import Singleton
from revu.application.config import get_logger, get_settings
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HTTPGatewayAttemptLimitExceeded,
    HttpGatewayError,
)

logger = get_logger(name=__name__)


class HttpClientGateway(Singleton):
    def __init__(self) -> None:
        self.timeout = get_settings().HTTP_CLIENT_TIMEOUT or 10.0
        self._client = httpx.AsyncClient(timeout=self.timeout)
        self.attempts = get_settings().HTTP_CLIENT_REQUEST_ATTEMPTS or 3

    async def _request(
        self,
        method: Literal["GET", "POST"],
        url: str,
        json: Any | None = None,
        headers: Mapping[str, str] | None = None,
        expect_json: bool = True,
    ) -> Any:
        attempts = self.attempts

        for i in range(attempts):
            try:
                resp = await self._client.request(
                    method=method,
                    url=url,
                    json=json,
                    headers=headers,
                )

                if resp.status_code == 429 or 500 <= resp.status_code < 600:
                    raise HttpGatewayError(f"HTTP {resp.status_code} from {url}")

                if expect_json:
                    if resp.content:
                        try:
                            payload = resp.json()
                        except Exception:
                            resp.raise_for_status()
                            raise HttpGatewayError(f"Non-JSON response from {url}: {resp.text[:300]}")
                    else:
                        payload = None

                    resp.raise_for_status()
                    return payload
                else:
                    resp.raise_for_status()
                    return resp.content
            except (httpx.TransportError, HttpGatewayError) as e:
                logger.warning(f"http error: {e}")
                if i < attempts - 1:
                    continue

                raise HTTPGatewayAttemptLimitExceeded()

        return None

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


def get_http_gateway() -> HttpClientGateway:
    return HttpClientGateway()
