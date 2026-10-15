import asyncio
from dataclasses import replace
from unittest.mock import ANY, AsyncMock

import httpx
import pytest
from openai import APITimeoutError, BadRequestError, InternalServerError, RateLimitError
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

import revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter as adapter_module
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    FIRST_BACKOFF,
    MAX_BACKOFF,
    OpenAICompatibleAdapter,
)
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    _sleep as real_sleep,
)
from tests.conftest import make_ai_profile

REQUEST = httpx.Request("POST", "https://cheap.example.com/v1/chat/completions")


def _status_error(kind, status, **headers):
    return kind(f"HTTP {status}", response=httpx.Response(status, headers=headers, request=REQUEST), body=None)


TIMEOUT = APITimeoutError(request=REQUEST)
SERVER_ERROR = _status_error(InternalServerError, 500)
TOO_MANY_REQUESTS = _status_error(RateLimitError, 429, **{"retry-after": "7"})
REFUSAL = _status_error(BadRequestError, 400)

MESSAGES = [
    ChatCompletionSystemMessageParam(role="system", content="system_prompt"),
    ChatCompletionUserMessageParam(role="user", content="user_prompt"),
]


@pytest.fixture(autouse=True)
def sleeper(monkeypatch):
    """Capture the waits between attempts instead of sleeping through them."""
    fake = AsyncMock()
    monkeypatch.setattr(adapter_module, "_sleep", fake)

    return fake


def _adapter(http_gateway, profile=None):
    adapter = OpenAICompatibleAdapter(http_client=http_gateway, profile=profile or _profile())
    adapter._openai_client = AsyncMock()

    return adapter


def _profile():
    return make_ai_profile(
        name="cheap",
        vendor=AIProviderEnum.OPENAI_COMPATIBLE,
        base_url="https://cheap.example.com/v1",
        model="qwen",
    )


async def test_openai_compatible_adapter_returns_sdk_response(http_gateway):
    fake_response = AsyncMock()

    adapter = OpenAICompatibleAdapter(http_client=http_gateway, profile=_profile())
    adapter._openai_client = AsyncMock()
    adapter._openai_client.chat.completions.parse.return_value = fake_response

    messages = [
        ChatCompletionSystemMessageParam(role="system", content="system_prompt"),
        ChatCompletionUserMessageParam(role="user", content="user_prompt"),
    ]

    resp = await adapter.get_chat_response(messages=messages)

    assert resp is fake_response
    assert adapter.model == "qwen"
    adapter._openai_client.chat.completions.parse.assert_awaited_once_with(
        model="qwen", messages=messages, response_format=ANY
    )


async def test_a_transient_failure_is_retried(http_gateway, caplog):
    """A request that never got a verdict is worth asking again."""
    adapter = _adapter(http_gateway)
    adapter.profile = replace(adapter.profile, max_retries=4)
    adapter._openai_client.chat.completions.parse.side_effect = [TIMEOUT, "the answer"]

    with caplog.at_level("WARNING"):
        resp = await adapter.get_chat_response(messages=MESSAGES)

    assert resp == "the answer"
    assert adapter._openai_client.chat.completions.parse.await_count == 2
    # The retry is visible: an operator sees the attempts, not just the outcome.
    assert "attempt 1 of 5" in caplog.text


async def test_a_refusal_is_not_repeated(http_gateway):
    """Repeating a refusal spends the whole prompt again for the same answer."""
    adapter = _adapter(http_gateway)
    adapter._openai_client.chat.completions.parse.side_effect = REFUSAL

    with pytest.raises(BadRequestError):
        await adapter.get_chat_response(messages=MESSAGES)

    assert adapter._openai_client.chat.completions.parse.await_count == 1


async def test_the_attempts_run_out_and_the_error_comes_back(http_gateway, caplog):
    adapter = _adapter(http_gateway, profile=replace(_profile(), max_retries=2))
    adapter._openai_client.chat.completions.parse.side_effect = SERVER_ERROR

    with caplog.at_level("WARNING"):
        with pytest.raises(InternalServerError):
            await adapter.get_chat_response(messages=MESSAGES)

    assert adapter._openai_client.chat.completions.parse.await_count == 3
    assert "after 3 attempts" in caplog.text


async def test_a_host_that_says_retry_after_is_believed(http_gateway, sleeper):
    adapter = _adapter(http_gateway)
    adapter._openai_client.chat.completions.parse.side_effect = [TOO_MANY_REQUESTS, "the answer"]

    await adapter.get_chat_response(messages=MESSAGES)

    sleeper.assert_awaited_once_with(7.0)


def test_the_backoff_grows_and_is_jittered():
    first = OpenAICompatibleAdapter._backoff(1, TIMEOUT)
    third = OpenAICompatibleAdapter._backoff(3, TIMEOUT)

    assert FIRST_BACKOFF * 0.5 <= first <= FIRST_BACKOFF
    assert third > first
    assert OpenAICompatibleAdapter._backoff(20, TIMEOUT) <= MAX_BACKOFF


def test_the_sdk_does_not_retry_on_its_own(http_gateway):
    """Its retries are silent and would multiply with ours into a count nobody chose."""
    adapter = OpenAICompatibleAdapter(http_client=http_gateway, profile=_profile())

    assert adapter._openai_client.max_retries == 0


def test_the_model_gets_the_profiles_timeout(http_gateway):
    profile = replace(_profile(), timeout=42.0)

    adapter = OpenAICompatibleAdapter(http_client=http_gateway, profile=profile)

    assert adapter._openai_client.timeout == 42.0


def test_a_failure_without_a_response_falls_back_to_our_own_backoff():
    """A connection that never happened carries no headers to believe."""
    assert OpenAICompatibleAdapter._backoff(1, TIMEOUT) <= FIRST_BACKOFF


def test_a_retry_after_that_is_a_date_falls_back_to_our_own_backoff():
    """RFC 7231 allows an HTTP date there, and we do not parse it."""
    dated = _status_error(RateLimitError, 429, **{"retry-after": "Wed, 21 Oct 2015 07:28:00 GMT"})

    assert OpenAICompatibleAdapter._backoff(1, dated) <= FIRST_BACKOFF


async def test_the_sleep_helper_is_the_only_real_wait():
    """Everything else is patched; this is the line that would actually wait."""
    await real_sleep(0)


async def test_an_answer_that_never_ends_is_cut_off(http_gateway, caplog):
    """The HTTP timeout is the gap between chunks, so a chatty model can run forever.

    One review sat behind exactly that for minutes while the log looked healthy: the
    response headers had arrived, so the request looked answered, and the body simply
    kept coming. The deadline is what makes the profile's timeout mean one request —
    generation included — and a retry is a fresh attempt rather than more waiting.
    """

    async def never_ends(*args, **kwargs):
        await asyncio.sleep(30)

    adapter = _adapter(http_gateway, profile=replace(_profile(), timeout=0.01, max_retries=1))
    adapter._openai_client.chat.completions.parse.side_effect = never_ends

    with caplog.at_level("WARNING"):
        with pytest.raises(TimeoutError, match="did not answer within"):
            await adapter.get_chat_response(messages=MESSAGES)

    assert adapter._openai_client.chat.completions.parse.await_count == 2
    assert "attempt 1 of 2" in caplog.text
