import asyncio
import random

from openai import (
    APIConnectionError,
    AsyncClient,
    InternalServerError,
    Omit,
    RateLimitError,
)
from openai.types.chat import (
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
    ParsedChatCompletion,
)
from pydantic import BaseModel

from revu.application.config import get_logger
from revu.application.entities.config import AIProfileConfig
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway

logger = get_logger(name=__name__)

#: Failures worth repeating: the request never got a verdict from the model, so the
#: same question may well get an answer next time. A reply the model refused to give
#: — a schema it cannot satisfy, a context too long for it — is deliberately absent:
#: repeating that spends the whole prompt again for the same refusal. `TimeoutError`
#: is the deadline below, and is transient by construction: another attempt starts
#: over instead of waiting on an answer that may never end.
TRANSIENT_FAILURES = (APIConnectionError, RateLimitError, InternalServerError, TimeoutError)

#: The wait between attempts: doubled each time, capped, and jittered. Several
#: connections can share one provider, and without jitter their retries line up.
FIRST_BACKOFF = 1.0
MAX_BACKOFF = 30.0


async def _sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _retry_after(exc: BaseException) -> float | None:
    """The `Retry-After` the host asked for, when it sent one."""
    response = getattr(exc, "response", None)
    header = response.headers.get("retry-after") if response is not None else None

    if header is None:
        return None

    try:
        return max(0.0, float(header))
    except ValueError:
        # An HTTP date, which we do not parse: fall back to our own backoff.
        return None


class OpenAICompatibleAdapter:
    def __init__(self, http_client: HttpClientGateway, profile: AIProfileConfig):
        self._http_client = http_client
        self.profile = profile
        self._openai_client = AsyncClient(
            api_key=profile.api_key,
            # The SDK is typed against its own httpx build, which is not the
            # one we depend on; the boundary tests drive the real client through
            # our transport, so the mismatch is in the stubs, not at runtime.
            http_client=self._http_client.get_client(),  # type: ignore[arg-type]
            base_url=profile.base_url,
            # Our HTTP client is built for the Git hosts and its timeout is far too
            # short for a model reading a whole diff; the SDK takes its own here.
            timeout=profile.timeout,
            # The SDK's retries are silent, and would multiply with ours into a
            # product nobody chose. Ours are counted and logged instead.
            max_retries=0,
        )
        self.model = profile.model

    async def get_chat_response(
        self,
        messages: list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam],
        response_model: type[BaseModel] | Omit = None,  # type: ignore
    ) -> ParsedChatCompletion:
        if response_model is None:
            response_model = Omit()

        attempt = 1
        attempts = self.profile.max_retries + 1

        while True:
            try:
                return await self._parse(messages, response_model)
            except TRANSIENT_FAILURES as exc:
                if attempt >= attempts:
                    logger.warning("the model did not answer after %d attempts: %r", attempts, exc)

                    raise

                delay = self._backoff(attempt, exc)
                logger.warning(
                    "the model did not answer (attempt %d of %d): %r; retrying in %.1fs",
                    attempt,
                    attempts,
                    exc,
                    delay,
                )
                await _sleep(delay)
                attempt += 1

    async def _parse(
        self,
        messages: list[ChatCompletionUserMessageParam | ChatCompletionSystemMessageParam],
        response_model: type[BaseModel] | Omit,
    ) -> ParsedChatCompletion:
        """Ask once, with a deadline on the whole answer.

        The HTTP timeout measures the gap between two chunks, not the length of an
        answer: a model that keeps generating never trips it, and a review can sit
        there for as long as the model keeps talking — one did, for minutes, while the
        log looked healthy. This is the bound that makes `AI_PROVIDER_TIMEOUT` mean
        what it says: one request to the model, however long the model spends writing.
        """
        try:
            async with asyncio.timeout(self.profile.timeout):
                return await self._openai_client.chat.completions.parse(
                    model=self.model,  # type: ignore
                    messages=messages,
                    response_format=response_model,
                )
        except TimeoutError as exc:
            raise TimeoutError(f"the model did not answer within {self.profile.timeout:.0f}s") from exc

    @staticmethod
    def _backoff(attempt: int, exc: BaseException) -> float:
        """How long to wait before the next attempt.

        A host that says `Retry-After` is believed — it knows when it will be ready —
        and otherwise the wait doubles, capped, with jitter so that several
        connections do not come back at the same instant.
        """
        asked = _retry_after(exc)

        if asked is not None:
            return asked

        return min(FIRST_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF) * random.uniform(0.5, 1.0)
