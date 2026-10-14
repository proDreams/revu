from unittest.mock import AsyncMock

import httpx
import pytest

import revu.infrastructure.http_client.http_client_gateway as gateway_module
from revu.application.entities.exceptions.http_gateway_exceptions import (
    HTTPGatewayAttemptLimitExceeded,
    HttpGatewayError,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway
from revu.infrastructure.http_client.http_client_gateway import _sleep as real_sleep


@pytest.fixture(autouse=True)
def sleeper(monkeypatch):
    """Capture backoff waits instead of sleeping through them."""
    fake = AsyncMock()
    monkeypatch.setattr(gateway_module, "_sleep", fake)
    return fake


def _gateway(client_request) -> HttpClientGateway:
    """Build a gateway whose transport returns or raises the given responses.

    A list is consumed in order; a bare exception is raised on every call; a
    bare response is returned on every call.
    """
    gateway = HttpClientGateway()

    if isinstance(client_request, list) or isinstance(client_request, BaseException):
        gateway._client.request = AsyncMock(side_effect=client_request)
    else:
        gateway._client.request = AsyncMock(return_value=client_request)

    return gateway


async def test_request_returns_json():
    gateway = _gateway(httpx.Response(200, json={"ok": True}))

    result = await gateway._request("GET", "https://example.com")

    assert result == {"ok": True}
    gateway._client.request.assert_awaited_once_with(method="GET", url="https://example.com", json=None, headers=None)


async def test_request_returns_raw_content_when_json_is_not_expected():
    gateway = _gateway(httpx.Response(200, content=b"test content"))

    result = await gateway._request(method="GET", url="https://example.com", expect_json=False)

    assert result == b"test content"


async def test_request_returns_none_for_an_empty_body():
    gateway = _gateway(httpx.Response(200))

    assert await gateway._request(method="GET", url="https://example.com") is None


async def test_zero_request_attempts_makes_no_call():
    gateway = _gateway(httpx.Response(200, json={"ok": True}))
    gateway.attempts = 0

    assert await gateway._request(method="GET", url="https://example.com", expect_json=False) is None
    gateway._client.request.assert_not_awaited()


async def test_non_retryable_error_is_not_repeated():
    """A 4xx never becomes a success by repeating it (it used to be retried 3 times)."""
    gateway = _gateway(httpx.Response(404, text="test error message"))
    gateway.attempts = 3

    with pytest.raises(HttpGatewayError) as exc_info:
        await gateway._request(method="GET", url="https://example.com")

    assert "404" in str(exc_info.value)
    assert "test error message" in str(exc_info.value)
    assert gateway._client.request.await_count == 1


async def test_get_retries_a_retryable_status():
    responses = [httpx.Response(503, text="unavailable"), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 3

    assert await gateway._request("GET", "https://example.com") == {"ok": True}
    assert gateway._client.request.await_count == 2


async def test_post_is_not_retried_on_a_server_error():
    """A 500 may mean the comment was created, and a retry would duplicate it."""
    gateway = _gateway(httpx.Response(500, text="boom"))
    gateway.attempts = 3

    with pytest.raises(HttpGatewayError):
        await gateway.post(url="https://example.com", payload={"body": "review"})

    assert gateway._client.request.await_count == 1


async def test_post_retries_when_the_server_did_not_process_it():
    responses = [httpx.Response(503), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 3

    assert await gateway.post(url="https://example.com", payload={"body": "review"}) == {"ok": True}
    assert gateway._client.request.await_count == 2


async def test_get_retries_a_transport_error():
    responses = [httpx.TransportError("Temporary network issue"), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 2

    assert await gateway._request("GET", "https://example.com") == {"ok": True}
    assert gateway._client.request.await_count == 2


async def test_post_retries_when_the_request_was_never_sent():
    responses = [httpx.ConnectError("connection refused"), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 2

    assert await gateway.post(url="https://example.com", payload={"body": "review"}) == {"ok": True}
    assert gateway._client.request.await_count == 2


async def test_post_does_not_retry_after_a_read_timeout():
    """The request may already have been applied, so repeating it is unsafe."""
    gateway = _gateway(httpx.ReadTimeout("timed out"))
    gateway.attempts = 3

    with pytest.raises(HTTPGatewayAttemptLimitExceeded):
        await gateway.post(url="https://example.com", payload={"body": "review"})

    assert gateway._client.request.await_count == 1


async def test_attempt_limit_is_reported_after_repeated_transport_errors():
    gateway = _gateway(httpx.TransportError("down"))
    gateway.attempts = 2

    with pytest.raises(HTTPGatewayAttemptLimitExceeded) as exc_info:
        await gateway._request("GET", "https://example.com")

    assert "Limit exceeded. Last error: down" in str(exc_info.value)
    assert gateway._client.request.await_count == 2


async def test_transport_errors_are_retried_up_to_the_limit():
    gateway = _gateway(httpx.TransportError("still down"))
    gateway.attempts = 3

    with pytest.raises(HTTPGatewayAttemptLimitExceeded):
        await gateway._request("GET", "https://example.com")

    assert gateway._client.request.await_count == 3


async def test_retry_after_header_is_honoured(sleeper):
    responses = [httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 2

    await gateway._request("GET", "https://example.com")

    sleeper.assert_awaited_once_with(2.0)


async def test_an_unparsable_retry_after_falls_back_to_exponential_backoff(sleeper):
    """Retry-After may also be an HTTP date, which is not worth parsing here."""
    responses = [
        httpx.Response(429, headers={"Retry-After": "Wed, 21 Oct 2015 07:28:00 GMT"}),
        httpx.Response(200, json={"ok": True}),
    ]
    gateway = _gateway(responses)
    gateway.attempts = 2
    gateway.backoff = 0.25

    await gateway._request("GET", "https://example.com")

    sleeper.assert_awaited_once_with(0.25)


async def test_sleep_helper_only_waits_for_positive_delays():
    """The real helper (the fixture replaces it for the other tests)."""
    await real_sleep(0)
    await real_sleep(0.001)


async def test_backoff_grows_exponentially(sleeper):
    responses = [httpx.Response(503), httpx.Response(503), httpx.Response(200, json={"ok": True})]
    gateway = _gateway(responses)
    gateway.attempts = 3
    gateway.backoff = 0.5

    await gateway._request("GET", "https://example.com")

    assert [call.args[0] for call in sleeper.await_args_list] == [0.5, 1.0]


async def test_non_json_response_is_not_retried():
    gateway = _gateway(httpx.Response(200, content=b"{not json}"))
    gateway.attempts = 3

    with pytest.raises(HttpGatewayError) as exc_info:
        await gateway._request(method="GET", url="https://example.com", expect_json=True)

    assert "Non-JSON response from https://example.com" in str(exc_info.value)
    assert gateway._client.request.await_count == 1


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
