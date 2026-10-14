"""Boundary tests that drive the real SDK clients through a mock transport.

The unit tests replace the adapter with an ``AsyncMock``, so they cannot catch a
wrong assumption about the SDK's HTTP contract — which is exactly how
``responses.parse(text_format=None)`` shipped broken. These tests exercise the
real ``openai`` client and assert on what actually goes over the wire.
"""

import json
from contextlib import asynccontextmanager

import httpx
import pytest

from revu.infrastructure.ai_providers.openai.openai_adapter import OpenAIAdapter
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_adapter import (
    OpenAICompatibleAdapter,
)
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

pytestmark = pytest.mark.unit

REVIEW_PAYLOAD = {
    "general_comment": "общий комментарий",
    "comments": [{"path": "app.py", "line": 7, "side": "RIGHT", "body": "замечание"}],
}


def _responses_body(text: str) -> dict:
    return {
        "id": "resp_1",
        "object": "response",
        "created_at": 1,
        "model": "gpt-4.1-mini",
        "status": "completed",
        "output": [
            {
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            }
        ],
        "parallel_tool_calls": True,
        "tool_choice": "auto",
        "tools": [],
    }


def _chat_body(text: str) -> dict:
    return {
        "id": "chatcmpl_1",
        "object": "chat.completion",
        "created": 1,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
    }


@asynccontextmanager
async def boundary_gateway(handler):
    """A gateway whose real httpx client is replaced by a mock transport.

    The client is swapped before the SDK wraps it, so the SDK talks to the
    transport while the gateway still owns the object it closes.
    """
    gateway = HttpClientGateway()
    await gateway._client.aclose()
    gateway._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    try:
        yield gateway
    finally:
        await gateway.aclose()


async def test_openai_comment_mode_omits_text_format():
    """C1: `text_format=None` made the SDK raise, and `text` must not be sent."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        seen["url"] = str(request.url)
        return httpx.Response(200, json=_responses_body("✅ Код выглядит хорошо."))

    async with boundary_gateway(handler) as gateway:
        port = OpenAIPort(adapter=OpenAIAdapter(http_client=gateway))
        result = await port.get_comment_response(diff="diff --git a/x b/x", pr_title="t")

    assert result == "✅ Код выглядит хорошо."
    assert seen["url"].endswith("/responses")
    assert "text" not in seen["body"]
    assert seen["body"]["model"] == "gpt-4.1-mini"


async def test_openai_inline_mode_requests_and_parses_a_json_schema():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json=_responses_body(json.dumps(REVIEW_PAYLOAD, ensure_ascii=False)))

    async with boundary_gateway(handler) as gateway:
        port = OpenAIPort(adapter=OpenAIAdapter(http_client=gateway))
        result = await port.get_inline_response(diff="d", git_provider="github", pr_title="t")

    assert seen["body"]["text"]["format"]["type"] == "json_schema"
    assert seen["body"]["text"]["format"]["strict"] is True
    assert result.general_comment == "общий комментарий"
    assert result.comments[0].line == 7
    assert result.comments[0].side == "RIGHT"


async def test_openai_compatible_comment_mode_sends_no_response_format(settings):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json=_chat_body("текст ревью"))

    async with boundary_gateway(handler) as gateway:
        port = OpenAICompatiblePort(adapter=OpenAICompatibleAdapter(http_client=gateway))
        result = await port.get_comment_response(diff="d", pr_title="t")

    assert result == "текст ревью"
    assert "response_format" not in seen["body"]


async def test_openai_compatible_inline_mode_requests_and_parses_a_json_schema(settings):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json=_chat_body(json.dumps(REVIEW_PAYLOAD, ensure_ascii=False)))

    async with boundary_gateway(handler) as gateway:
        port = OpenAICompatiblePort(adapter=OpenAICompatibleAdapter(http_client=gateway))
        result = await port.get_inline_response(diff="d", git_provider="github", pr_title="t")

    assert seen["body"]["response_format"]["type"] == "json_schema"
    assert result.comments[0].body == "замечание"
