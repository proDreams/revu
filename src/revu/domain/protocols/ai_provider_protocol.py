from typing import Protocol, runtime_checkable

from revu.domain.entities.dto.ai_provider_dto import ReviewResponseDTO
from revu.domain.entities.dto.review_task_dto import ReviewTask


class AIProviderProtocol(Protocol):
    """An AI provider bound to one credential set.

    Implementations are stateless beyond their client and model: the prompt, the
    requested output format and the diff all arrive with the task, so one
    instance can serve every git connection that references its profile.
    """

    async def get_comment_response(self, task: ReviewTask) -> str:
        """Return a single review comment for the whole pull request."""
        ...

    async def get_inline_response(self, task: ReviewTask) -> ReviewResponseDTO:
        """Return a structured review with per-line comments."""
        ...


@runtime_checkable
class CloseableAIProvider(Protocol):
    """A port that owns its HTTP transport and must release it on shutdown.

    Ports backed by the shared :class:`HttpClientGateway` deliberately do **not**
    implement this: the OpenAI SDK closes the ``httpx`` client it was handed, and
    that client is shared by every connection, so closing one profile would break
    all of them (see docs/multi-provider-design.md §4.8).
    """

    async def aclose(self) -> None:
        """Release the underlying client."""
        ...
