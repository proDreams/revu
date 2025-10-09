from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from revu.application.entities.exceptions.http_gateway_exceptions import (
    HTTPGatewayAttemptLimitExceeded,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway


async def test_request_returns_json():
    gateway = HttpClientGateway()
    mock_response = AsyncMock()
    mock_response.is_error = False
    mock_response.content = b'{"ok": true}'
    mock_response.json = Mock(return_value={"ok": True})

    gateway._client.request = AsyncMock(return_value=mock_response)

    result = await gateway._request("GET", "https://example.com")

    assert result == {"ok": True}
    gateway._client.request.assert_awaited_once_with(method="GET", url="https://example.com", json=None, headers=None)


async def test_request_returns_error():
    gateway = HttpClientGateway()
    mock_response = AsyncMock()
    mock_response.is_error = True
    mock_response.status_code = 404
    mock_response.text = "test error message"
    gateway._client.request = AsyncMock(return_value=mock_response)
    gateway.attempts = 1

    url = "https://example.com"

    with pytest.raises(HTTPGatewayAttemptLimitExceeded) as exc_info:
        await gateway._request(method="GET", url=url)

    assert "test error message" in str(exc_info.value)
    assert "404" in str(exc_info.value)


async def test_request_fail_on_non_json_response():
    gateway = HttpClientGateway()
    mock_response = AsyncMock()
    mock_response.is_error = False
    mock_response.content = b"{test invalid json}"
    mock_response.text = "{test invalid json}"
    mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
    gateway._client.request = AsyncMock(return_value=mock_response)
    gateway.attempts = 1

    url = "https://example.com"

    with pytest.raises(HTTPGatewayAttemptLimitExceeded) as exc_info:
        await gateway._request(method="GET", url=url, expect_json=True)

    assert f"Non-JSON response from {url}" in str(exc_info.value)


async def test_request_return_no_content():
    gateway = HttpClientGateway()
    mock_response = AsyncMock()
    mock_response.is_error = False
    mock_response.content = None
    gateway._client.request = AsyncMock(return_value=mock_response)
    gateway.attempts = 1

    url = "https://example.com"

    result = await gateway._request(method="GET", url=url, expect_json=True)

    assert result is None


async def test_request_return_content():
    gateway = HttpClientGateway()
    mock_response = AsyncMock()
    mock_response.is_error = False
    mock_response.content = b"test content"
    gateway._client.request = AsyncMock(return_value=mock_response)
    gateway.attempts = 1

    url = "https://example.com"

    result = await gateway._request(method="GET", url=url, expect_json=False)

    assert result == b"test content"


async def test_retry_request():
    gateway = HttpClientGateway()
    gateway.attempts = 2

    mock_response_success = AsyncMock()
    mock_response_success.is_error = False
    mock_response_success.content = b'{"ok": true}'
    mock_response_success.json = Mock(return_value={"ok": True})

    async def fake_request(*args, **kwargs):
        if not hasattr(fake_request, "called"):
            fake_request.called = True
            raise httpx.TransportError("Temporary network issue")
        return mock_response_success

    gateway._client.request = AsyncMock(side_effect=fake_request)

    result = await gateway._request("GET", "https://example.com")

    assert result == {"ok": True}
    assert gateway._client.request.await_count == 2


async def test_zero_request_attempts():
    gateway = HttpClientGateway()
    gateway.attempts = 0
    gateway._client.request = AsyncMock()

    url = "https://example.com"

    result = await gateway._request(method="GET", url=url, expect_json=False)

    assert result is None


async def test_post_calls_request_with_correct_args(monkeypatch):
    gateway = HttpClientGateway()
    mock_request = AsyncMock(return_value={"ok": True})
    gateway._request = mock_request

    url = "https://example.com"
    payload = {"test": "test"}

    result = await gateway.post(url=url, payload=payload, headers={"x": "y"})

    assert result == {"ok": True}

    mock_request.assert_awaited_once_with(
        method="POST",
        url=url,
        json=payload,
        headers={"x": "y"},
    )


async def test_get_calls_request_with_correct_args(monkeypatch):
    gateway = HttpClientGateway()
    mock_request = AsyncMock(return_value={"ok": True})
    gateway._request = mock_request

    url = "https://example.com"

    result = await gateway.get(url=url, headers={"x": "z"}, expect_json=False)

    assert result == {"ok": True}
    mock_request.assert_awaited_once_with(
        method="GET",
        url=url,
        headers={"x": "z"},
        expect_json=False,
    )
